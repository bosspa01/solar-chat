/**
 * หน้า Login / Register
 * แสดงก่อนเข้าใช้งานแชท ถ้า login สำเร็จจะเรียก onLogin(token, username)
 */
import { useState } from "react";
import "./Login.css";

const API_BASE = import.meta.env.VITE_RAG_API_BASE;

export default function Login({ onLogin }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    const trimmedUsername = username.trim();
    if (!trimmedUsername || !password) {
      setError("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน");
      return;
    }
    if (mode === "register" && password !== confirmPassword) {
      setError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
      return;
    }

    setLoading(true);
    try {
      if (mode === "register") {
        const res = await fetch(`${API_BASE}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: trimmedUsername, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "สมัครสมาชิกไม่สำเร็จ");
      }

      // ทั้งสองโหมดจบด้วยการ login เพื่อรับ token
      const loginRes = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: trimmedUsername, password }),
      });
      const loginData = await loginRes.json();
      if (!loginRes.ok) throw new Error(loginData.detail || "เข้าสู่ระบบไม่สำเร็จ");

      onLogin(loginData.access_token, loginData.username);
    } catch (err) {
      setError(err.message || "เกิดข้อผิดพลาด กรุณาลองใหม่");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>☀️ Solar Q&A</h1>
        <p className="auth-subtitle">
          {mode === "login" ? "เข้าสู่ระบบเพื่อดูประวัติแชทของคุณ" : "สร้างบัญชีใหม่เพื่อเริ่มใช้งาน"}
        </p>

        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            ชื่อผู้ใช้
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              disabled={loading}
              placeholder="เช่น mon123"
            />
          </label>
          <label>
            รหัสผ่าน
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              disabled={loading}
              placeholder="อย่างน้อย 6 ตัวอักษร"
            />
          </label>
          {mode === "register" && (
            <label>
              ยืนยันรหัสผ่าน
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                disabled={loading}
              />
            </label>
          )}

          {error ? <p className="auth-error">{error}</p> : null}

          <button type="submit" className="btn btn-primary auth-submit" disabled={loading}>
            {loading ? "กำลังดำเนินการ…" : mode === "login" ? "เข้าสู่ระบบ" : "สมัครสมาชิก"}
          </button>
        </form>

        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode((m) => (m === "login" ? "register" : "login"));
            setError("");
          }}
          disabled={loading}
        >
          {mode === "login" ? "ยังไม่มีบัญชี? สมัครสมาชิก" : "มีบัญชีอยู่แล้ว? เข้าสู่ระบบ"}
        </button>
      </div>
    </div>
  );
}
