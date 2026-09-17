# Backend image สำหรับ Solar Q&A API (FastAPI + RAG)
# ใช้ python:3.11-slim ให้ตรงกับที่ระบุใน README (Python 3.11+)
FROM python:3.11-slim

WORKDIR /app

# build-essential จำเป็นสำหรับบาง wheel ที่ต้อง compile (เช่น บาง dependency ของ sentence-transformers/tokenizers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# copy requirements ก่อนเพื่อให้ Docker cache layer นี้ไว้ (ไม่ต้อง pip install ใหม่ทุกครั้งที่โค้ดเปลี่ยน)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy โค้ด backend และ PDF ที่ใช้ทำ RAG (ไม่ copy node_modules/.venv/ฯลฯ - ดู .dockerignore)
COPY rag_api.py auth_db.py ./
COPY solar_pdf ./solar_pdf
COPY Sarabun-Regular.ttf ./

ENV PYTHONUNBUFFERED=1

# Railway/Render จะฉีด env var PORT มาให้ตอน runtime - bind 0.0.0.0 เสมอสำหรับ container
EXPOSE 8000
CMD ["sh", "-c", "uvicorn rag_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
