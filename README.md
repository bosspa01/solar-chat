# Solar Chat (RAG + Local Free Model)

โปรเจคนี้เป็นแชตบอทถามตอบด้านพลังงานแสงอาทิตย์ โดยใช้:
- Frontend: React + Vite
- Backend: FastAPI + FAISS (RAG)
- LLM: Ollama local model (ใช้ฟรีบนเครื่องตัวเอง)

## Requirements

- Node.js `20.17+` (แนะนำ 20.19+)
- Python `3.11+`
- Ollama

## Environment

ไฟล์ `.env` ตัวอย่างในโปรเจค:

```env
VITE_RAG_API_BASE=http://localhost:8000
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
```

## Run on Current Machine

### 1) ติดตั้งและเปิด Ollama

```powershell
ollama pull llama3.1:8b
ollama serve
```

> ถ้า `ollama` ไม่เจอใน PATH บน Windows ให้ใช้:
> `C:\Users\<your-user>\AppData\Local\Programs\Ollama\ollama.exe`

### 2) รัน Backend (FastAPI)

```powershell
cd C:\Users\hp\Downloads\solar-chat
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn rag_api:app --host 127.0.0.1 --port 8000
```

### 3) รัน Frontend (Vite)

เปิด terminal ใหม่:

```powershell
cd C:\Users\hp\Downloads\solar-chat
npm install
npm run dev
```

เปิดเว็บที่ `http://127.0.0.1:5173`

## ย้ายไปรันเครื่องอื่นต้องทำยังไง

ทำตามลำดับนี้:

1. Clone/Copy โฟลเดอร์โปรเจคไปเครื่องใหม่
2. ติดตั้ง Node.js, Python, Ollama
3. สร้าง `.env` ตามตัวอย่างด้านบน
4. รัน `ollama pull llama3.1:8b` (โหลดโมเดลครั้งแรก)
5. ติดตั้ง backend dependencies:
   - `pip install -r requirements.txt`
6. ติดตั้ง frontend dependencies:
   - `npm install`
7. เปิด 3 process พร้อมกัน:
   - `ollama serve`
   - `python -m uvicorn rag_api:app --host 127.0.0.1 --port 8000`
   - `npm run dev`

## Login / Register (ประวัติแชทต่อผู้ใช้)

ตอนนี้ต้อง **สมัครสมาชิกและเข้าสู่ระบบ** ก่อนถึงจะแชทได้ ประวัติแชททั้งหมดผูกกับบัญชีและเก็บถาวรใน `app.db` (SQLite ที่ backend สร้างขึ้นเองอัตโนมัติตอนรันครั้งแรก ไม่ต้องติดตั้งอะไรเพิ่ม)

- Backend มี dependency ใหม่: `PyJWT`, `passlib[bcrypt]`, `bcrypt` (อยู่ใน `requirements.txt` แล้ว รัน `pip install -r requirements.txt` ตามปกติ)
- `.env` มีตัวแปรใหม่ `JWT_SECRET` ไว้เซ็นโทเค็น login (สุ่มไว้ให้แล้ว เปลี่ยนเป็นค่าของคุณเองได้)
- Endpoint ใหม่: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `GET /sessions`, `GET /sessions/{id}/messages`, `DELETE /sessions/{id}`
- `app.db` ไม่ถูกผูกขึ้น git (อยู่ใน `.gitignore` แล้ว)

## Quick Health Checks

- Ollama: `http://127.0.0.1:11434/api/tags`
- Backend docs: `http://127.0.0.1:8000/docs`
- Frontend: `http://127.0.0.1:5173`
