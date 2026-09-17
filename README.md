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

## Deploy ขึ้นจริง (Vercel + Railway)

โปรเจกต์นี้โหลดโมเดล embedding ไว้ใน RAM ตลอด (~1GB+) และต้องเก็บ `app.db` อย่างถาวร ดังนั้น free tier เปล่าๆ (512MB RAM, ไม่มี disk ถาวร) ของ Render/Railway จะไม่เพียงพอ ข้อมูลด้านล่างเป็นขั้นตอนที่ทำจริงได้:

### 1) Push ขึ้น GitHub

โปรเจกต์นี้เป็น git repo แล้ว (commit แรกเสร็จแล้ว) เหลือแค่สร้าง repo เปล่าบน GitHub แล้ว push:

```powershell
git remote add origin https://github.com/<your-username>/solar-chat.git
git branch -M main
git push -u origin main
```

### 2) Backend → Railway (~$5/เดือน Hobby plan)

1. เข้า [railway.app](https://railway.app) → New Project → Deploy from GitHub repo → เลือก repo นี้ (Railway จะเจอ `Dockerfile` และ build ให้เอง)
2. อีก tab **Variables** ใส่ env var (ดูรายการเต็มใน `.env.example`):
   - `GROQ_API_KEY`, `GROQ_MODEL`
   - `JWT_SECRET` — **สุ่มใหม่** อย่าเอาค่าเดียวกาบที่ใช้ dev เครื่องนี้ (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `CORS_ORIGINS` — เว้นว่างไว้ก่อน จนกว่าจะรู้ URL ของ Vercel (ข้อ 3)
   - `AUTH_DB_PATH=/data/app.db`
   - `CACHE_CHUNKS_PATH=/data/chunks_cache.pkl`
   - `CACHE_VECTOR_DB_PATH=/data/vector_db_cache.pkl`
3. อีก tab **Settings → Volumes** → สร้าง volume ใหม่ mount ที่ `/data` (เก็บ `app.db` + cache ให้อยู่คงทุกครั้งที่ redeploy)
4. Deploy — ครั้งแรกจะช้ากว่าปกติ (ต้อง build embedding ใหม่เพราะเป็น volume เปล่า) ครั้งต่อไปจะเร็วขึ้นเยอะเพราะใช้ cache ที่เก็บไว้ใน volume
5. Railway จะออก URL ให้ เช่น `https://solar-chat-production.up.railway.app` — เก็บ URL นี้ไว้ใช้อ้างอง frontend

### 3) Frontend → Vercel (ฟรี)

1. เข้า [vercel.com](https://vercel.com) → Add New Project → Import repo นี้จาก GitHub (Vercel จะเจอ `vercel.json` และตั้งค่า build ให้เอง)
2. ใน **Environment Variables** ใส่ `VITE_RAG_API_BASE` = URL ของ Railway จากข้อ 2 (เช่น `https://solar-chat-production.up.railway.app`)
3. Deploy — ได้ URL เช่น `https://solar-chat.vercel.app`
4. กลับไปที่ Railway → อัปเดต `CORS_ORIGINS` เป็น URL ของ Vercel จากข้อนี้ แล้ว redeploy backend

เสร็จแล้ว! เข้า URL ของ Vercel → สมัครสมาชิกและเริ่มแชทได้เลย

### ทางเลือกฟรีจริง (ต้องดูแล server เอง)

สมัคร Oracle Cloud "Always Free" VM (ARM, สูงสุด 24GB RAM ฟรีตลอดชีพ) — เหมาะหากอยากเรียนรู้เกี่ยวกับ DevOps (ต้องตั้ง nginx, HTTPS เองด้วย `docker compose up -d` จาก `Dockerfile` ที่มีอยู่แล้วได้เลย)
