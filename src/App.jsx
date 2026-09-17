/**
 * แอปพลิเคชัน Solar Q&A Chat
 * 
 * อินเตอร์เฟส chatbot ที่อิงตาม React สำหรับถามคำถามเกี่ยวกับเซลล์แสงอาทิตย์และพลังงาน
 * คุณสมบัติ:
 * - ต้อง login / register ก่อนใช้งาน
 * - ประวัติแชทหลายส่วน เก็บถาวรใน backend ผูกกับบัญชีผู้ใช้ (ไม่ใช่ localStorage)
 * - การเรนเดอร์ markdown แบบเรียลไทม์พร้อมขอบเขตข้อผิดพลาด
 * - แถบด้านข้างแบบตอบสนองสำหรับประวัติแชท
 * - ปุ่มลัด (Enter เพื่อส่ง, Shift+Enter สำหรับบรรทัดใหม่)
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import Login from "./Login.jsx";
import "./App.css";

// ============================================================================
// การตั้งค่าและค่าคงที่
// ============================================================================

const API_BASE = import.meta.env.VITE_RAG_API_BASE;
const TOKEN_KEY = "solar_chat_token";
const USERNAME_KEY = "solar_chat_username";
const DEFAULT_GREETING = "สวัสดี! ถามฉันเกี่ยวกับ Solar Cell ได้เลย";

// ============================================================================
// ฟังก์ชันยูทิลิตี้
// ============================================================================

/**
 * สร้างส่วนแชทใหม่ (ในเครื่อง ยังไม่บันทึกลง backend จนกว่าจะส่งข้อความแรก)
 */
function createSection() {
  const now = Date.now();
  return {
    id: crypto.randomUUID(),
    title: "แชทใหม่",
    createdAt: now,
    updatedAt: now,
    messages: [{ role: "assistant", content: DEFAULT_GREETING }],
    loaded: true,
  };
}

/**
 * สร้างชื่อสั้นจากข้อความแชทแรกของผู้ใช้
 * @param {string} text - ข้อความของผู้ใช้
 * @returns {string} ชื่อที่ตัดทอน (อักขระสูงสุด 28 ตัว)
 */
function shortTitleFromText(text) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "แชทใหม่";
  return cleaned.length > 28 ? `${cleaned.slice(0, 28)}...` : cleaned;
}

/**
 * จัดรูปแบบเวลาเป็นสตริงตามท้องถิ่นไทย
 * @param {number} timestamp - Unix timestamp เป็นมิลลิวินาที
 * @returns {string} วันและเวลาที่จัดรูปแบบ
 */
function formatSectionTime(timestamp) {
  return new Date(timestamp).toLocaleString("th-TH", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ============================================================================
// ไอคอน SVG
// ============================================================================

/**
 * ไอคอนดวงอาทิตย์สำหรับแบรนดิ้ง (ใช้เป็นอวาตาร์บอท)
 */
function SunIcon() {
  return (
    <svg className="brand-icon" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="6" fill="currentColor" />
      <g stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none">
        {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
          <line
            key={deg}
            x1="16"
            y1="3"
            x2="16"
            y2="6"
            transform={`rotate(${deg} 16 16)`}
          />
        ))}
      </g>
    </svg>
  );
}

/**
 * อวาตาร์ผู้ใช้ - แสดงไอคอนคน
 */
function UserAvatar() {
  return (
    <div className="avatar avatar-user" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    </div>
  );
}

/**
 * อวาตาร์บอท - แสดงไอคอนดวงอาทิตย์
 */
function BotAvatar() {
  return (
    <div className="avatar avatar-bot" aria-hidden="true">
      <SunIcon />
    </div>
  );
}

// ============================================================================
// ขอบเขตข้อผิดพลาดและคอมโพเนนต์ Markdown
// ============================================================================

/**
 * ขอบเขตข้อผิดพลาดสำหรับการเรนเดอร์ markdown
 * จัดการข้อผิดพลาดในการแปลง markdown อย่างสง่างามและแสดงข้อความทดแทน
 */
class MarkdownBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error("การเรนเดอร์ Markdown ล้มเหลว", error);
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return <div className="markdown-fallback">{this.props.fallback}</div>;
    }

    return this.props.children;
  }
}

/**
 * จัดรูปแบบการตอบสนอง markdown ของผู้ช่วยเพื่อการเรนเดอร์ที่ถูกต้อง
 * สะท้อนการจัดรูปแบบแบ็กเอนด์เพื่อให้เชื่อมโยงกัน
 * 
 * หมายเหตุ: การดำเนินการจัดรูปแบบเดียวกันกับ format_answer_markdown() ของแบ็กเอนด์
 * ให้ markdown สอดคล้องระหว่างการตอบสนอง API และการแสดงผลหน้าเว็บ
 * 
 * @param {string} content - เนื้อหาดิบจากผู้ช่วย
 * @returns {string} Markdown ที่จัดรูปแบบ
 */
function normalizeAssistantMarkdown(content) {
  let formatted = content
    .replace(/\r\n/g, "\n")
    .replace(/\\r\\n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\u00a0/g, " ");

  // เพิ่มการขึ้นบรรทัดใหม่ก่อนหัวข้อ รายการ และข้อความที่จัดรูปแบบ
  formatted = formatted
    .replace(/\s*(#{1,6}\s+)/g, "\n\n$1")
    .replace(/\s*(---+)\s*/g, "\n\n$1\n\n")
    .replace(/([:：])\s*(#{1,6}\s+)/g, "$1\n\n$2")
    .replace(/([:：])\s*(\d+\.\s+)/g, "$1\n\n$2")
    .replace(/([^\n])\s+(\d+\.\s+)/g, "$1\n\n$2")
    .replace(/([^\n])\s+([*-]\s+\*\*)/g, "$1\n$2")
    .replace(/([^\n])\s+([*-]\s+)/g, "$1\n$2")
    .replace(/(\*\*[^\n]+?\*\*)\s+(\*\*[^\n]+?\*\*)/g, "$1\n$2")
    .replace(/(\n\d+\.\s[^\n:]{0,80}:)\s+/g, "$1\n")
    .replace(/\n{3,}/g, "\n\n");

  return formatted.trim();
}

/**
 * ตัวเรนเดอร์เนื้อหาข้อความ
 * จัดการข้อความของทั้งผู้ใช้และผู้ช่วยพร้อม markdown support
 */
function MessageContent({ content, role }) {
  const safeContent = typeof content === "string" ? content : String(content ?? "");

  // ข้อความของผู้ใช้แสดงเป็นข้อความธรรมดา
  if (role === "user") {
    return <span>{safeContent}</span>;
  }

  // ข้อความของผู้ช่วยจัดรูปแบบและเรนเดอร์เป็น markdown
  const markdownContent = normalizeAssistantMarkdown(safeContent);

  return (
    <MarkdownBoundary resetKey={markdownContent} fallback={safeContent}>
      <div className="markdown-content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          components={{
            // เปิดลิงก์ในแท็บใหม่
            a: ({ node, ...props }) => (
              <a {...props} target="_blank" rel="noopener noreferrer" />
            ),
          }}
        >
          {markdownContent}
        </ReactMarkdown>
      </div>
    </MarkdownBoundary>
  );
}


// ============================================================================
// คอมโพเนนต์แอปหลัก
// ============================================================================

/**
 * คอมโพเนนต์แอปพลิเคชันหลักประกอบด้วย:
 * - หน้า login/register เป็นด่านแรกก่อนเข้าใช้งาน
 * - การจัดการแชทหลายส่วนพร้อมแถบด้านข้าง (ประวัติเก็บใน backend ผูกกับบัญชี)
 * - การซิงโครไนซ์ข้อความแบบเรียลไทม์
 * - เลย์เอาต์ตอบสนองพร้อมปุ่มสลับแถบด้านข้าง
 */
export default function App() {
  // ========================================
  // สถานะการยืนยันตัวตน
  // ========================================

  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [username, setUsername] = useState(() => localStorage.getItem(USERNAME_KEY) || "");

  // ========================================
  // การจัดการสถานะแชท
  // ========================================

  // ส่วนแชท - แต่ละส่วนคือการสนทนาแยกต่างหาก (โหลดจาก backend หลัง login)
  const [sections, setSections] = useState([]);

  // ID ส่วนการทำงานที่ใช้งานอยู่ในปัจจุบัน
  const [activeSectionId, setActiveSectionId] = useState(null);

  // ค่าอินพุตข้อความปัจจุบัน
  const [input, setInput] = useState("");

  // สถานะการโหลดขณะรอการตอบสนอง API
  const [loading, setLoading] = useState(false);

  // สถานะการโหลดรายการแชทครั้งแรกหลัง login
  const [sessionsLoading, setSessionsLoading] = useState(false);

  // มองเห็นแถบด้านข้างบนมือถือ
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // อ้างอิงสำหรับการจัดการ DOM
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  // ========================================
  // ตัวช่วยเรียก API แบบแนบ Authorization header
  // ========================================

  function authHeaders() {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  /**
   * ออกจากระบบ (ใช้ทั้งตอนกดปุ่ม logout และตอน token หมดอายุ/ไม่ถูกต้อง)
   */
  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    setToken(null);
    setUsername("");
    setSections([]);
    setActiveSectionId(null);
  }

  /**
   * เรียก fetch พร้อม Authorization header, ถ้า 401 ให้ logout อัตโนมัติ
   */
  async function authFetch(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers || {}),
      },
    });
    if (res.status === 401) {
      handleLogout();
    }
    return res;
  }

  function handleLogin(newToken, newUsername) {
    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(USERNAME_KEY, newUsername);
    setToken(newToken);
    setUsername(newUsername);
  }

  // ========================================
  // ค่าที่ท่องจำ
  // ========================================

  // เรียงลำดับส่วนตามอัปเดตล่าสุด
  const sortedSections = useMemo(
    () => [...sections].sort((a, b) => b.updatedAt - a.updatedAt),
    [sections]
  );

  // รับวัตถุส่วนการทำงานที่ใช้งานอยู่
  const activeSection = useMemo(() => {
    if (!sections.length) return null;
    return sections.find((s) => s.id === activeSectionId) ?? sections[0];
  }, [sections, activeSectionId]);

  // ========================================
  // ผลกระทบ - โหลดประวัติแชทจาก backend หลัง login
  // ========================================

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    setSessionsLoading(true);

    (async () => {
      try {
        const res = await authFetch("/sessions");
        if (!res.ok) throw new Error("โหลดประวัติแชทไม่สำเร็จ");
        const data = await res.json();
        if (cancelled) return;

        if (!Array.isArray(data) || data.length === 0) {
          // ผู้ใช้ใหม่ยังไม่มีแชทเลย - เตรียม section เปล่าไว้ในเครื่องก่อน
          const fresh = createSection();
          setSections([fresh]);
          setActiveSectionId(fresh.id);
          return;
        }

        const loadedSections = data.map((s) => ({
          id: s.id,
          title: s.title,
          createdAt: new Date(s.created_at).getTime(),
          updatedAt: new Date(s.updated_at).getTime(),
          messages: [],
          loaded: false,
        }));
        setSections(loadedSections);
        setActiveSectionId(loadedSections[0].id);
      } catch {
        // เรียก backend ไม่สำเร็จ - ให้มีอย่างน้อยหนึ่ง section ใช้งานได้ในเครื่อง
        const fresh = createSection();
        setSections([fresh]);
        setActiveSectionId(fresh.id);
      } finally {
        if (!cancelled) setSessionsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // โหลดข้อความของ section ที่กำลังเปิดอยู่ (ถ้ายังไม่เคยโหลด)
  useEffect(() => {
    if (!token || !activeSection || activeSection.loaded) return;

    let cancelled = false;
    const sectionId = activeSection.id;

    (async () => {
      try {
        const res = await authFetch(`/sessions/${sectionId}/messages`);
        if (!res.ok) throw new Error("โหลดข้อความไม่สำเร็จ");
        const msgs = await res.json();
        if (cancelled) return;

        updateSectionById(sectionId, (section) => ({
          ...section,
          loaded: true,
          messages:
            msgs.length > 0
              ? msgs.map((m) => ({ role: m.role, content: m.content }))
              : [{ role: "assistant", content: DEFAULT_GREETING }],
        }));
      } catch {
        if (!cancelled) {
          updateSectionById(sectionId, (section) => ({
            ...section,
            loaded: true,
            messages: [{ role: "assistant", content: DEFAULT_GREETING }],
          }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeSection?.id]);

  // ตรวจสอบให้แน่ใจว่าเรามีส่วนการทำงานที่ใช้งานอยู่เสมอ
  useEffect(() => {
    if (!token) return;
    if (sessionsLoading) return;

    if (!sections.length) {
      const next = createSection();
      setSections([next]);
      setActiveSectionId(next.id);
      return;
    }

    if (!activeSectionId || !sections.some((s) => s.id === activeSectionId)) {
      setActiveSectionId(sections[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sections, activeSectionId, token, sessionsLoading]);

  // เลื่อนอัตโนมัติไปยังข้อความล่าสุดเมื่อข้อความใหม่มาถึงหรือการโหลดสิ้นสุด
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSection?.messages, loading]);

  // ========================================
  // ฟังก์ชันตัวจัดการ
  // ========================================

  /**
   * อัปเดตส่วนตามรหัส ID โดยใช้ฟังก์ชันตัวอัปเดต
   * @param {string} sectionId - ส่วนที่จะอัปเดต
   * @param {Function} updater - ฟังก์ชันที่นำส่วนและส่งกลับส่วนที่อัปเดต
   */
  function updateSectionById(sectionId, updater) {
    setSections((prev) => prev.map((s) => (s.id === sectionId ? updater(s) : s)));
  }

  /**
   * สร้างและสลับไปยังส่วนแชทใหม่ (จะถูกบันทึกลง backend ตอนส่งข้อความแรก)
   */
  function createNewSection() {
    const next = createSection();
    setSections((prev) => [next, ...prev]);
    setActiveSectionId(next.id);
    setInput("");
    textareaRef.current?.focus();
  }

  /**
   * ส่งข้อความไปยัง API และเพิ่มการตอบสนอง
   * จัดการการตรวจสอบความถูกต้องของข้อความ การเรียก API และการจัดการข้อผิดพลาด
   */
  async function sendMessage() {
    if (!activeSection) return;

    const currentSectionId = activeSection.id;
    const text = input.trim();
    if (!text || loading) return;

    const hasUserMessage = activeSection.messages.some((m) => m.role === "user");
    const titleForSection = hasUserMessage ? activeSection.title : shortTitleFromText(text);

    // อัปเดตส่วนด้วยข้อความของผู้ใช้และตั้งชื่อหากเป็นข้อความแรก
    updateSectionById(currentSectionId, (section) => ({
      ...section,
      title: titleForSection,
      updatedAt: Date.now(),
      messages: [...section.messages, { role: "user", content: text }],
    }));

    setInput("");
    setLoading(true);

    try {
      // ส่งข้อความไปยัง backend API
      const res = await authFetch("/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          session_id: currentSectionId,
          title: hasUserMessage ? undefined : titleForSection,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`API error ${res.status}: ${errText}`);
      }

      // เพิ่มการตอบสนอง API ลงในข้อความ
      const data = await res.json();
      updateSectionById(currentSectionId, (section) => ({
        ...section,
        updatedAt: Date.now(),
        messages: [...section.messages, { role: "assistant", content: data.answer }],
      }));
    } catch (e) {
      // แสดงข้อความข้อผิดพลาดเมื่อล้มเหลว
      updateSectionById(currentSectionId, (section) => ({
        ...section,
        updatedAt: Date.now(),
        messages: [
          ...section.messages,
          { role: "assistant", content: `ขอโทษนะ เกิดข้อผิดพลาด: ${e.message}` },
        ],
      }));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  /**
   * จัดการปุ่ม Enter เพื่อส่งข้อความ Shift+Enter สำหรับบรรทัดใหม่
   */
  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  /**
   * ลบข้อความทั้งหมดออกจากส่วนปัจจุบันและรีเซ็ตชื่อ
   */
  function clearCurrentSection() {
    if (!activeSection) return;
    authFetch("/clear", {
      method: "POST",
      body: JSON.stringify({ session_id: activeSection.id }),
    }).catch(() => {});
    updateSectionById(activeSection.id, (section) => ({
      ...section,
      title: "แชทใหม่",
      updatedAt: Date.now(),
      messages: [{ role: "assistant", content: DEFAULT_GREETING }],
    }));
    setInput("");
    textareaRef.current?.focus();
  }

  /**
   * ลบส่วนหรือรีเซ็ตหากเป็นส่วนสุดท้าย
   */
  function deleteSection(sectionId) {
    if (sections.length === 1) {
      clearCurrentSection();
      return;
    }
    authFetch(`/sessions/${sectionId}`, { method: "DELETE" }).catch(() => {});
    setSections((prev) => prev.filter((s) => s.id !== sectionId));
    if (activeSectionId === sectionId) {
      const next = sections.find((s) => s.id !== sectionId);
      if (next) setActiveSectionId(next.id);
    }
  }

  // ========================================
  // สถานะที่ได้มา
  // ========================================

  const apiReady = Boolean(API_BASE);

  // ========================================
  // การแสดงผล
  // ========================================

  // ยังไม่ login - แสดงหน้า login/register แทนหน้าแชท
  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="page">
      <div className={`app-shell ${sidebarOpen ? "app-shell--sidebar-open" : ""}`}>
        {/* แถบด้านข้าง - ประวัติแชทและนำทาง */}
        <aside className="sidebar" aria-label="ประวัติแชท">
          <div className="sidebar-head">
            <div className="brand compact-brand">
              <div className="brand-mark">
                <SunIcon />
              </div>
              <div className="brand-text">
                <h1>Solar Q&A</h1>
                <p className="tagline">ประวัติแชท</p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-new-chat"
              onClick={createNewSection}
              disabled={loading}
            >
              + New chat
            </button>
          </div>

          {/* ผู้ใช้ปัจจุบันและปุ่มออกจากระบบ */}
          <div className="sidebar-user">
            <span className="sidebar-user-name" title={username}>
              👤 {username}
            </span>
            <button type="button" className="btn btn-ghost sidebar-logout" onClick={handleLogout}>
              ออกจากระบบ
            </button>
          </div>

          {/* ตัวบ่งชี้สถานะ API */}
          <div className="sidebar-status">
            <span
              className={`api-pill ${apiReady ? "api-pill--ok" : "api-pill--warn"}`}
              title={apiReady ? "เชื่อม API แล้ว" : "ตั้งค่า VITE_RAG_API_BASE"}
            >
              {apiReady ? "พร้อมใช้งาน" : "ยังไม่ตั้งค่า API"}
            </span>
          </div>

          {/* ประวัติแชท - ส่วนต่างๆ */}
          <section className="sections" aria-label="รายการ section แชท">
            {sessionsLoading ? (
              <p className="sections-loading">กำลังโหลดประวัติแชท…</p>
            ) : (
              sortedSections.map((section) => {
                const isActive = section.id === activeSection?.id;
                const lastMessage = section.messages.at(-1)?.content ?? "ยังไม่มีข้อความ";

                return (
                  <article
                    key={section.id}
                    className={`section-row ${isActive ? "section-row--active" : ""}`}
                  >
                    <button
                      type="button"
                      className="section-main"
                      onClick={() => {
                        setActiveSectionId(section.id);
                        setSidebarOpen(false);
                      }}
                    >
                      <p className="section-title">{section.title}</p>
                      <p className="section-preview">{lastMessage}</p>
                    </button>
                    <button
                      type="button"
                      className="section-delete"
                      onClick={() => deleteSection(section.id)}
                      aria-label={`ลบ section ${section.title}`}
                      disabled={loading && isActive}
                    >
                      ×
                    </button>
                  </article>
                );
              })
            )}
          </section>
        </aside>

        {/* บานหลัก - แผงแชท */}
        <div className="chat-pane">
          {/* แถบด้านบน - ชื่อเรื่องและการควบคุม */}
          <header className="chat-topbar">
            <button
              type="button"
              className="btn btn-ghost btn-menu"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="เปิดประวัติแชท"
            >
              ☰
            </button>
            <div className="chat-topbar-title">
              <h2>{activeSection?.title ?? "แชท"}</h2>
              <p>{activeSection ? `อัปเดต ${formatSectionTime(activeSection.updatedAt)}` : ""}</p>
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={clearCurrentSection}
              disabled={loading || !activeSection}
            >
              ล้างแชท
            </button>
          </header>

          {/* พื้นที่ข้อความ - ประวัติข้อความที่เลื่อนได้ */}
          <main className="chat" aria-live="polite" aria-relevant="additions">
            <div className="chat-inner">
              {(activeSection?.messages ?? []).map((msg, idx) => (
                <article
                  key={idx}
                  className={`msg msg--${msg.role}`}
                >
                  {msg.role === "user" ? <UserAvatar /> : <BotAvatar />}
                  <div className="msg-body">
                    <span className="msg-label">
                      {msg.role === "user" ? "คุณ" : "ผู้ช่วย"}
                    </span>
                    <div className={`bubble bubble--${msg.role}`}>
                      <MessageContent content={msg.content} role={msg.role} />
                    </div>
                  </div>
                </article>
              ))}
              
              {/* ตัวบ่งชี้พิมพ์ขณะรอการตอบสนอง */}
              {loading ? (
                <article className="msg msg--assistant msg--typing" aria-busy="true">
                  <BotAvatar />
                  <div className="msg-body">
                    <span className="msg-label">ผู้ช่วย</span>
                    <div className="bubble bubble--assistant bubble--typing" aria-label="กำลังพิมพ์">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </div>
                  </div>
                </article>
              ) : null}
              
              {/* จุดยึดสำหรับการเลื่อนอัตโนมัติ */}
              <div ref={chatEndRef} />
            </div>
          </main>

          {/* พื้นที่ป้อนข้อมูล - ตัวแต่งข้อความ */}
          <footer className="composer">
            <div className="composer-field">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="พิมพ์คำถามเกี่ยวกับ Solar cell…"
                rows={1}
                disabled={loading || !apiReady || !activeSection}
                aria-label="ข้อความถาม"
              />
              <p className="composer-hint">
                Enter เพื่อส่ง · Shift+Enter ขึ้นบรรทัดใหม่
              </p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={sendMessage}
              disabled={loading || !apiReady || !input.trim() || !activeSection}
            >
              {loading ? (
                <span className="btn-spinner" aria-hidden="true" />
              ) : (
                <svg className="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinejoin="round" />
                </svg>
              )}
              <span>{loading ? "กำลังส่ง" : "ส่ง"}</span>
            </button>
          </footer>
        </div>
      </div>
    </div>
  );
}
