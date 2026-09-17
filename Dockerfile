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

# ติดตั้ง PyTorch แบบ CPU-only ก่อน (รันบน CPU เท่านั้น ไม่มี GPU) - ถ้าไม่ทำแบบนี้ pip จะดึงแพ็กเกจ CUDA/GPU
# มาด้วยหลาย GB โดยไม่จำเป็น ทำให้ image ใหญ่และ build ช้ามาก
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# copy โค้ด backend และ PDF ที่ใช้ทำ RAG (ไม่ copy node_modules/.venv/ฯลฯ - ดู .dockerignore)
COPY rag_api.py auth_db.py ./
COPY solar_pdf ./solar_pdf
COPY Sarabun-Regular.ttf ./

# ฝัง cache ที่สร้างไว้ล่วงหน้า (ด้วย build_deploy_cache.py บนเครื่อง dev) เข้า image โดยตรง
# เพื่อหลีกเลี่ยงการคำนวณ embedding ตอน container เริ่มทำงาน (ช้า/เสี่ยง OOM บนเครื่อง RAM จำกัด)
COPY deploy_chunks_cache.pkl ./chunks_cache.pkl
COPY deploy_vector_db_cache.pkl ./vector_db_cache.pkl

ENV PYTHONUNBUFFERED=1

# Railway/Render จะฉีด env var PORT มาให้ตอน runtime - bind 0.0.0.0 เสมอสำหรับ container
EXPOSE 8000
CMD ["sh", "-c", "uvicorn rag_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
