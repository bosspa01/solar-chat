"""
Solar Q&A API - ชาตบอท RAG สำหรับด้านพลังงานแสงอาทิตย์
ดึงข้อมูลจากเอกสารและให้คำตอบจาก AI เกี่ยวกับเซลล์แสงอาทิตย์และการผลิตพลังงาน
"""
import sys
import os

# บน Windows console บางเครื่องใช้ codepage ที่ไม่รองรับ emoji/อักขระพิเศษ สั่งบังคับให้ stdout/stderr เป็น UTF-8 กันโปรแกรมคราชตอน print()
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from pydantic import BaseModel
import auth_db
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from collections import defaultdict
import glob
import pickle
from pypdf import PdfReader
import re
import requests

# ============================================================================
# การตั้งค่า
# ============================================================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
LLM_TEMPERATURE = 0.4
MAX_HISTORY_TURNS = 8

# เส้นทาง cache เพื่อโหลดเร็วขึ้นในครั้งต่อไป — กำหนดเป็น env var ได้เพื่อชี้ไปที่ persistent volume ตอน deploy
CACHE_CHUNKS_PATH = os.getenv("CACHE_CHUNKS_PATH", "chunks_cache.pkl")
CACHE_VECTOR_DB_PATH = os.getenv("CACHE_VECTOR_DB_PATH", "vector_db_cache.pkl")

# แหล่งข้อมูล PDF
PDF_PATHS = ["solar_pdf", "."]

# embedding model - ดีกว่า MiniLM สำหรับภาษาไทย
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# ============================================================================
# ตั้งค่า FastAPI
# ============================================================================
app = FastAPI(title="Solar Q&A API", description="ชาตบอท RAG สำหรับด้านพลังงานแสงอาทิตย์")

# CORS: กำหนดโดเมน frontend ที่อนุญาตได้จริงผ่าน env var CORS_ORIGINS (คั่นด้วย , ถ้าหลายโดเมน)
# ตอน dev ไม่ต้องตั้งค่าอะไร จะ fallback เป็น "*" (เปิดทั้งหมด) แต่ตอน deploy จริง ควรกำหนดเป็นโดเมน frontend จริงเสมอ
_cors_env = os.getenv("CORS_ORIGINS", "*").strip()
CORS_ORIGINS = ["*"] if _cors_env in ("", "*") else [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# สร้างตาราง users / sessions / messages ถ้ายังไม่มี
auth_db.init_db()


@app.get("/health")
def health_check():
    """Health check endpoint สำหรับ hosting platform (Railway/Render) ตรวจสอบว่า service ยังมีชีวิตอยู่"""
    return {"status": "ok"}

# ============================================================================
# แบบจำลองข้อมูล
# ============================================================================
class ChatReq(BaseModel):
    message: str
    session_id: str
    title: str | None = None  # ชื่อ section (ส่งมาตอนข้อความแรกของแชทใหม่)

class ClearReq(BaseModel):
    session_id: str

class RegisterReq(BaseModel):
    username: str
    password: str

class LoginReq(BaseModel):
    username: str
    password: str

# ============================================================================
# ฟังก์ชันโหลดข้อมูล
# ============================================================================


def load_pdf_docs() -> list:
    """
    โหลดและแปลงไฟล์ PDF ทีละหน้าพร้อมเก็บหมายเลขหน้าใน metadata
    เพื่อให้สามารถอ้างอิงแหล่งข้อมูลได้แม่นยำขึ้น
    """
    pdf_files = []
    for folder in PDF_PATHS:
        if not os.path.isdir(folder):
            continue
        pdf_files.extend(glob.glob(os.path.join(folder, "*.pdf")))

    pdf_files = sorted(set(pdf_files))

    docs = []
    if not pdf_files:
        print("⚠️ ไม่พบไฟล์ PDF ในโฟลเดอร์ solar_pdf หรือโฟลเดอร์ราก")
        return docs

    for path in pdf_files:
        try:
            reader = PdfReader(path)
            filename = os.path.basename(path)
            for page_num, page in enumerate(reader.pages, start=1):
                content = (page.extract_text() or "").strip()
                if content:
                    docs.append({
                        "source": filename,
                        "text": content,
                        "page": page_num,
                    })
        except Exception as e:
            print(f"⚠️ เกิดข้อผิดพลาดในการอ่าน PDF {path}: {e}")

    return docs


def build_chunks_with_metadata(docs: list) -> tuple:
    """
    แบ่งเอกสารเป็น chunks พร้อม metadata ที่มีชื่อไฟล์และหมายเลขหน้า
    chunk_size=1200 และ overlap=250 เหมาะสำหรับภาษาไทยที่ประโยคยาว
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=250)
    chunks = []
    metadatas = []

    for doc in docs:
        text = doc.get("text", "")
        source = doc.get("source", "ไม่ระบุ")
        page = doc.get("page")
        if not text.strip():
            continue

        for chunk in splitter.split_text(text):
            chunks.append(chunk)
            meta = {"source": source}
            if page:
                meta["page"] = page
            metadatas.append(meta)

    return chunks, metadatas


def load_or_build_chunks() -> tuple:
    """โหลด chunks จากแคช หรือสร้างจากเอกสารต้นฉบับ"""
    if os.path.exists(CACHE_CHUNKS_PATH):
        with open(CACHE_CHUNKS_PATH, "rb") as f:
            saved = pickle.load(f)
            print("✅ โหลด chunks จากแคช")

            if isinstance(saved, tuple) and len(saved) == 2:
                chunks, metadatas = saved
            elif isinstance(saved, list):
                chunks = saved
                metadatas = [{"source": "ไม่ระบุ"} for _ in chunks]
                print("⚠️ พบรูปแบบแคชเก่า กำลังแปลงเป็นรูปแบบใหม่พร้อมข้อมูลเมตา")
            else:
                raise ValueError("รูปแบบไม่ถูกต้องในแคช chunks")

            return chunks, metadatas

    docs = load_pdf_docs()
    chunks, metadatas = build_chunks_with_metadata(docs)

    with open(CACHE_CHUNKS_PATH, "wb") as f:
        pickle.dump((chunks, metadatas), f)
        print(f"✅ สร้างและเก็บแคช chunks ลง {CACHE_CHUNKS_PATH}")

    return chunks, metadatas


# ============================================================================
# เริ่มต้นฐานข้อมูลเวกเตอร์
# ============================================================================

chunks, chunk_metadatas = load_or_build_chunks()

if os.path.exists(CACHE_VECTOR_DB_PATH):
    with open(CACHE_VECTOR_DB_PATH, "rb") as f:
        vector_db = pickle.load(f)
        print(f"✅ โหลด vector_db จากแคช {CACHE_VECTOR_DB_PATH}")
else:
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_db = FAISS.from_texts(chunks, embeddings, metadatas=chunk_metadatas)

    with open(CACHE_VECTOR_DB_PATH, "wb") as f:
        pickle.dump(vector_db, f)
        print(f"✅ สร้างและเก็บแคช vector_db ลง {CACHE_VECTOR_DB_PATH}")


# ============================================================================
# ตั้งค่า System Prompt
# ============================================================================

system_prompt = """
คุณคือ "โซล่า" ที่ปรึกษาด้านโซลาร์เซลล์ที่เป็นกันเอง พูดภาษาไทยเป็นธรรมชาติเหมือนเพื่อนที่รู้เรื่องโซลาร์ดีมาก

สไตล์การคุย:
- พูดเป็นธรรมชาติ ไม่เป็นทางการเกินไป ใช้ "ครับ" ลงท้ายได้
- ถ้าคำถามไม่ชัด ให้ถามกลับก่อน เช่น "บ้านคุณใช้ไฟเดือนละเท่าไหร่ครับ?" แทนที่จะเดา
- จำบริบทการสนทนาก่อนหน้าได้ สามารถอ้างอิงสิ่งที่คุยไปแล้วได้เลย
- ถ้าตอบไปแล้วและผู้ใช้ถามต่อ ให้ต่อยอดจากคำตอบเดิม ไม่ต้องเริ่มใหม่
- แสดงความเข้าใจก่อนตอบ เช่น "เข้าใจครับ กรณีนี้..." หรือ "โอเคครับ ถ้าอย่างนั้น..."

การตอบ:
- เน้นประเด็นสำคัญก่อน แล้วขยายรายละเอียด
- ใช้ bullet หรือลำดับขั้นตอนเมื่อมีหลายข้อ แต่ไม่ต้องทำทุกคำตอบ
- ถ้ามีข้อมูลในเอกสาร ให้อ้างอิงชื่อไฟล์และหน้าด้วย เช่น "(คู่มือโซลาร์บ้าน หน้า 21)"
- ถ้าเอกสารไม่มีข้อมูล บอกตรงๆ แล้วแนะนำให้ถามผู้เชี่ยวชาญหน้างาน
- ถ้าถามเรื่องการคำนวณ ให้บอกว่าคำนวณแทนไม่ได้ แต่อธิบายวิธีคิดหรือสูตรได้

สิ่งที่ห้าม:
- อย่าแสร้งทำเป็นรู้ทั้งที่ไม่รู้
- อย่าตอบเรื่องนอกขอบเขตโซลาร์และพลังงาน
"""

# ============================================================================
# ฟังก์ชันตัวช่วย
# ============================================================================

def is_simple_math(text: str) -> bool:
    text = text.strip()
    if re.fullmatch(r"[0-9 \t\n\(\)\+\-\*/\.]+", text):
        return True
    return False


def wants_calculation(text: str) -> bool:
    t = text.lower().strip()
    calc_keywords = [
        "คำนวณ", "หาค่า", "เท่ากับเท่าไร", "เท่าไหร่", "กี่กิโลวัตต์", "กี่ kw",
        "กี่ kwh", "ประมาณกี่", "roi", "คืนทุน", "payback", "ต้นทุน", "ราคารวม",
        "แปลงหน่วย", "บวกลบ", "สมการ", "สูตร", "เทียบเท่า", "แปลงเป็น",
    ]
    if any(k in t for k in calc_keywords):
        return True
    if re.search(r"\d+\s*[\+\-\*/×÷]\s*\d+", t):
        return True
    return False


def extract_main_question(text: str) -> str:
    """สกัดคำถามหลักจากข้อความ"""
    if not text:
        return ""

    cleaned = re.sub(r"\s+", " ", text).strip()

    explicit_markers = [
        "อยากถามว่า", "คำถามคือ", "ขอถามว่า", "ช่วยตอบว่า", "อยากรู้ว่า",
    ]
    for marker in explicit_markers:
        if marker in cleaned:
            candidate = cleaned.split(marker, 1)[1].strip(" :,-")
            if candidate:
                return candidate

    if "?" in cleaned or "？" in cleaned:
        qparts = re.split(r"[?？]", cleaned)
        for part in reversed(qparts[:-1]):
            part = part.strip(" :,-")
            if part:
                return part + "?"

    parts = re.split(r"[\n\r]+|(?<=[\?\!？!])\s+|(?<=[\.])\s+", cleaned)
    parts = [p.strip() for p in parts if p.strip()]

    question_markers = [
        "?", "？", "อย่างไร", "ยังไง", "หรือไม่", "ไหม", "มั้ย",
        "อะไร", "ทำไม", "เท่าไร", "เท่าไหร่", "กี่", "ควร", "ต้อง", "เริ่ม",
    ]
    domain_markers = [
        "โซลาร์", "โซลาร์เซลล์", "solar", "solar cell", "panel", "inverter",
        "หลังคา", "ติดตั้ง", "พลังงานแสงอาทิตย์", "ค่าไฟ",
    ]

    scored = []
    for part in parts:
        score = 0
        lowered = part.lower()
        if any(marker in part for marker in question_markers):
            score += 3
        if any(marker in lowered for marker in domain_markers):
            score += 3
        if "ฉันอยากถาม" in part or "คำถาม" in part:
            score += 2
        if len(part) <= 160:
            score += 1
        scored.append((score, part))

    best_score, best_part = max(scored, key=lambda x: x[0], default=(0, cleaned))
    return best_part if best_score > 0 else cleaned


def extract_query_keywords(text: str) -> list:
    """
    ดึงคำสำคัญจากคำถามสำหรับ keyword matching
    ตัด token ยาวเกิน 15 ตัวออก เพราะมักเป็น Thai ที่พิมพ์ไม่มี space
    ซึ่งจะใช้ reverse check ใน docs_relevant_to_question แทน
    """
    cleaned = re.sub(r"[^0-9A-Za-zก-๙\s]", " ", text.lower())
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    stopwords = {
        "คือ", "และ", "หรือ", "ของ", "ที่", "ใน", "ได้", "ให้", "กับ", "จาก", "แล้ว",
        "ถ้า", "จะ", "ควร", "ต้อง", "ทำ", "ยังไง", "อย่างไร", "อะไร", "ฉัน", "ผม",
        "หน่อย", "ครับ", "ค่ะ", "คะ", "สวัสดี", "อยาก", "ถาม", "ว่า", "ช่วย",
        "the", "you", "provided", "appears", "data", "points", "from", "various",
        "sources", "represented", "each", "identifier", "timestamped", "entries",
    }
    keywords = [t for t in tokens if 3 <= len(t) <= 15 and t not in stopwords]
    return keywords[:8]


def docs_relevant_to_question(question: str, docs: list) -> bool:
    """
    ตรวจสอบแบบหยาบว่าเอกสารที่ดึงมามีเนื้อหาที่เกี่ยวกับคำถามหรือไม่
    รองรับ Thai ที่ไม่มี space โดยเช็คทั้งสองทิศทาง:
    - forward: keyword ของคำถามอยู่ใน doc
    - reverse: คำจาก doc อยู่ใน query (กรณี Thai พิมพ์ติดกัน)
    """
    keywords = extract_query_keywords(question)
    if not keywords:
        return True

    combined = " ".join((doc.page_content or "").lower() for doc in docs[:8])

    if any(keyword in combined for keyword in keywords):
        return True

    # reverse check สำหรับ Thai ที่พิมพ์ไม่มี space
    question_lower = question.lower()
    doc_words = [w for w in combined.split() if len(w) >= 3]
    return any(word in question_lower for word in doc_words[:100])


def filter_relevant_docs(question: str, docs: list) -> list:
    """
    คัดเอกสารที่เกี่ยวข้องกับคำถามโดยนับ keyword hits
    ถ้าไม่มี chunk ใดตรง keyword เลย ให้ fallback กลับไปใช้ top similarity แทน
    เพื่อป้องกันการตอบ "ไม่พบข้อมูล" เมื่อเอกสารจริงๆ มีคำตอบ
    """
    keywords = extract_query_keywords(question)
    if not keywords:
        return docs[:7]

    filtered = []
    for doc in docs:
        content = (doc.page_content or "").lower()
        hits = sum(1 for keyword in keywords if keyword in content)
        if hits > 0:
            filtered.append((hits, doc))

    # reverse check: คำจาก doc อยู่ใน query (Thai ไม่มี space)
    if not filtered:
        question_lower = question.lower()
        for doc in docs:
            content = (doc.page_content or "").lower()
            doc_words = [w for w in content.split() if len(w) >= 3]
            hits = sum(1 for w in doc_words if w in question_lower)
            if hits > 0:
                filtered.append((hits, doc))

    filtered.sort(key=lambda item: item[0], reverse=True)
    result = [doc for _, doc in filtered[:7]]

    # fallback: ถ้ายังไม่มี match เลย ใช้ top similarity แทน
    return result if result else docs[:7]


NO_DOC_ANSWER = (
    "ขออภัยครับ ในเอกสารที่ระบบมีอยู่ตอนนี้ **ไม่พบข้อมูลที่ตอบคำถามนี้ได้โดยตรง** "
    "หากมีไฟล์ PDF/ข้อมูลเพิ่มเติม ลองอัปโหลดหรือรัน `/rebuild` ให้ครับ "
    "หรือถามคำถามอื่นเกี่ยวกับโซลาร์ที่อยู่ในเอกสารได้เลยครับ"
)

CALC_DECLINE_ANSWER = (
    "ขออภัยครับ ผมไม่สามารถช่วยคำนวณตัวเลขหรือสมการให้ได้ "
    "แนะนำให้ใช้เครื่องคิดเลข/สเปรดชีต หรือปรึกษาวิศวกร/ผู้ติดตั้งที่มีข้อมูลหน้างานจริงครับ "
    "ถ้าต้องการ ถามเรื่องหลักการหรือขั้นตอนจากเอกสารได้เลยครับ"
)


def format_answer_markdown(text: str) -> str:
    """จัดรูปแบบคำตอบ Markdown"""
    if not text:
        return ""

    formatted = str(text)
    formatted = formatted.replace("\r\n", "\n")
    formatted = formatted.replace("\\r\\n", "\n")
    formatted = formatted.replace("\\n", "\n")
    formatted = formatted.replace(" ", " ")

    formatted = re.sub(r"\s*(#{1,6}\s+)", r"\n\n\1", formatted)
    formatted = re.sub(r"\s*(---+)\s*", r"\n\n\1\n\n", formatted)
    formatted = re.sub(r"([:：])\s*(#{1,6}\s+)", r"\1\n\n\2", formatted)
    formatted = re.sub(r"([:：])\s*(\d+\.\s+)", r"\1\n\n\2", formatted)
    formatted = re.sub(r"([^\n])\s+(\d+\.\s+)", r"\1\n\n\2", formatted)
    formatted = re.sub(r"([^\n])\s+([\*\-]\s+\*\*)", r"\1\n\2", formatted)
    formatted = re.sub(r"([^\n])\s+([\*\-]\s+)", r"\1\n\2", formatted)
    formatted = re.sub(r"(\*\*[^\n]+?\*\*)\s+(\*\*[^\n]+?\*\*)", r"\1\n\2", formatted)
    formatted = re.sub(r"(\n\d+\.\s[^\n:]{0,80}:)\s+", r"\1\n", formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)

    return formatted.strip()


def build_context_from_docs(docs: list) -> str:
    """สร้าง context สำหรับส่งให้ LLM พร้อมระบุหมายเลขหน้า"""
    context_parts = []
    for idx, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "ไม่ระบุ")
        page = doc.metadata.get("page")
        location = f"{source} หน้า {page}" if page else source
        context_parts.append(f"[{idx}] แหล่งข้อมูล: {location}\n{doc.page_content}")
    return "\n\n".join(context_parts)


def build_user_turn(question: str, docs: list) -> str:
    """สร้าง user message สำหรับส่ง LLM รวม doc context ถ้ามี"""
    if docs:
        context_text = build_context_from_docs(docs)
        return f"{question}\n\n---\nบริบทจากเอกสาร:\n{context_text}"
    return question


def generate_answer_with_groq(question: str, docs: list, history: list) -> str:
    """เรียก Groq API พร้อม conversation history"""
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    messages = history + [{"role": "user", "content": build_user_turn(question, docs)}]
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=1500,
        messages=[{"role": "system", "content": system_prompt}] + messages,
    )
    answer = completion.choices[0].message.content
    if not answer:
        raise RuntimeError("Groq ไม่ส่งคำตอบกลับมา")
    return answer


def generate_answer_with_claude(question: str, docs: list, history: list) -> str:
    """เรียก Claude API พร้อม conversation history และ prompt caching"""
    import anthropic
    client = anthropic.Anthropic()
    messages = history + [{"role": "user", "content": build_user_turn(question, docs)}]
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    return message.content[0].text


def generate_answer_with_ollama(question: str, docs: list, history: list) -> str:
    """เรียก Ollama local model พร้อม conversation history"""
    history_text = ""
    for msg in history[-6:]:
        role = "ผู้ใช้" if msg["role"] == "user" else "ผู้ช่วย"
        history_text += f"{role}: {msg['content']}\n"

    user_turn = build_user_turn(question, docs)
    full_prompt = f"{system_prompt}\n\n{history_text}ผู้ใช้: {user_turn}\nผู้ช่วย:"

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": LLM_MODEL, "prompt": full_prompt, "temperature": LLM_TEMPERATURE, "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    answer = resp.json().get("response", "")
    if not answer:
        raise RuntimeError("Ollama ไม่ส่งคำตอบกลับมา")
    return answer


def generate_answer(question: str, docs: list, history: list) -> str:
    """เลือก LLM ตาม API key: Groq → Claude → Ollama"""
    if os.getenv("GROQ_API_KEY"):
        return generate_answer_with_groq(question, docs, history)
    if os.getenv("ANTHROPIC_API_KEY"):
        return generate_answer_with_claude(question, docs, history)
    return generate_answer_with_ollama(question, docs, history)


# ============================================================================
# API ENDPOINTS - การยืนยันตัวตน (register / login)
# ============================================================================

@app.post("/auth/register")
def register(req: RegisterReq):
    """สมัครสมาชิกใหม่ - คืนค่า user ที่สร้างแล้ว (ยังไม่ได้ login ให้เรียก /auth/login ต่อ)"""
    user = auth_db.create_user(req.username, req.password)
    return {"status": "registered", "username": user["username"]}


@app.post("/auth/login")
def login(req: LoginReq):
    """เข้าสู่ระบบ - คืน JWT access token"""
    user = auth_db.authenticate_user(req.username, req.password)
    token = auth_db.create_access_token(user["id"], user["username"])
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}


@app.get("/auth/me")
def me(current_user: dict = Depends(auth_db.get_current_user)):
    """ตรวจสอบ token และคืนข้อมูลผู้ใช้ปัจจุบัน"""
    return current_user


# ============================================================================
# API ENDPOINTS - แชทและประวัติแชท (ต้อง login ก่อน)
# ============================================================================

@app.post("/chat")
def chat(req: ChatReq, current_user: dict = Depends(auth_db.get_current_user)):
    user_id = current_user["id"]

    # สร้าง session ถ้ายังไม่มี และตรวจว่าเป็นของ user คนนี้จริง
    auth_db.ensure_session(user_id, req.session_id, req.title or "แชทใหม่")
    if not auth_db.session_belongs_to_user(req.session_id, user_id):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงแชทนี้")

    main_question = extract_main_question(req.message)
    db_history = auth_db.get_session_messages(req.session_id)[-(MAX_HISTORY_TURNS * 2):]
    history = [{"role": m["role"], "content": m["content"]} for m in db_history]

    if is_simple_math(main_question) or wants_calculation(main_question):
        answer = CALC_DECLINE_ANSWER
        auth_db.add_message(req.session_id, "user", req.message)
        auth_db.add_message(req.session_id, "assistant", answer)
        auth_db.touch_session(req.session_id, req.title if not db_history else None)
        return {"answer": answer, "sources": [], "source_mention": ""}

    # ดึงเอกสารที่เกี่ยวข้อง — ถ้าไม่เจอเลยให้ส่ง history อย่างเดียว (อาจเป็น follow-up)
    docs = vector_db.similarity_search(main_question, k=15)
    if docs and docs_relevant_to_question(main_question, docs):
        docs = filter_relevant_docs(main_question, docs)
    else:
        docs = []

    sources = sorted(set([d.metadata.get("source", "ไม่ระบุ") for d in docs])) if docs else []

    try:
        answer = generate_answer(main_question, docs, history)
    except requests.exceptions.ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"เชื่อมต่อ Ollama ไม่ได้ที่ {OLLAMA_BASE_URL}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"เรียก LLM ไม่สำเร็จ: {e}") from e

    answer = format_answer_markdown(answer)

    # บันทึก history ลง SQLite (ผูกกับ session/user) — เก็บ message ดิบ ไม่เก็บ doc context
    auth_db.add_message(req.session_id, "user", req.message)
    auth_db.add_message(req.session_id, "assistant", answer)
    # ตั้งชื่อสมำหรับ section เฉพาะตอนข้อความแรก หลังจากนั้นแค่อัปเดต updated_at
    auth_db.touch_session(req.session_id, req.title if not db_history else None)

    return {
        "answer": answer,
        "sources": sources,
        "source_mention": ("ข้อมูลจาก: " + ", ".join(sources)) if sources else "",
    }


@app.post("/clear")
def clear_history(req: ClearReq, current_user: dict = Depends(auth_db.get_current_user)):
    """ล้าง conversation history ของ session นี้ (เก็บ session ไว้ ล้างเฉพาะข้อความ)"""
    if not auth_db.session_belongs_to_user(req.session_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงแชทนี้")
    auth_db.clear_session_messages(req.session_id)
    return {"status": "cleared"}


# ============================================================================
# API ENDPOINTS - ประวัติแชท (รายการ section ของผู้ใช้)
# ============================================================================

@app.get("/sessions")
def get_sessions(current_user: dict = Depends(auth_db.get_current_user)):
    """รายการแชททั้งหมดของผู้ใช้ที่ล็อกอินอยู่ (เรียงตาม updated_at)"""
    return auth_db.list_sessions(current_user["id"])


@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, current_user: dict = Depends(auth_db.get_current_user)):
    """ดึงข้อความทั้งหมดของแชท section หนึ่ง"""
    if not auth_db.session_belongs_to_user(session_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงแชทนี้")
    return auth_db.get_session_messages(session_id)


@app.delete("/sessions/{session_id}")
def remove_session(session_id: str, current_user: dict = Depends(auth_db.get_current_user)):
    """ลบ section แชททิ้งทั้งหมดอย่างถาวร"""
    if not auth_db.session_belongs_to_user(session_id, current_user["id"]):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงแชทนี้")
    auth_db.delete_session(session_id)
    return {"status": "deleted"}


@app.post("/rebuild")
def rebuild():
    """
    สร้างฐานข้อมูลเวกเตอร์และ RAG ใหม่ทั้งหมด
    จำเป็นต้องรันหลังจากเพิ่มไฟล์ PDF หรือเปลี่ยน embedding model
    """
    global chunks, chunk_metadatas, vector_db

    if os.path.exists(CACHE_CHUNKS_PATH):
        os.remove(CACHE_CHUNKS_PATH)
    if os.path.exists(CACHE_VECTOR_DB_PATH):
        os.remove(CACHE_VECTOR_DB_PATH)

    chunks, chunk_metadatas = load_or_build_chunks()

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_db = FAISS.from_texts(chunks, embeddings, metadatas=chunk_metadatas)

    with open(CACHE_VECTOR_DB_PATH, "wb") as f:
        pickle.dump(vector_db, f)

    return {
        "status": "สร้างเสร็จสิ้น",
        "chunk_count": len(chunks),
        "source_count": len(set([m.get("source", "ไม่ระบุ") for m in chunk_metadatas])),
    }
