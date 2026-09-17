"""
สคริปต์สร้าง cache (chunks + vector DB) ล่วงหน้าบนเครื่องนี้ (มี RAM/CPU เต็มที่)
แล้วนำไฟล์ที่ได้ไปฝังเข้า Docker image ตอน build แทนที่จะให้ server บน hosting
(ที่ RAM จำกัดมาก) ต้องมาคำนวณ embedding เองตอน container เริ่มทำงาน ซึ่งช้าและเสี่ยง OOM

ใช้ตอนไหน: รันสคริปต์นี้ทุกครั้งที่เพิ่ม/แก้ไขไฟล์ PDF ใน solar_pdf/ แล้ว commit ไฟล์
deploy_chunks_cache.pkl และ deploy_vector_db_cache.pkl เข้า git ก่อน deploy ใหม่

วิธีรัน: .\.venv\Scripts\python.exe build_deploy_cache.py
"""
import os

os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

import glob
import pickle
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

PDF_PATHS = ["solar_pdf", "."]
OUT_CHUNKS = "deploy_chunks_cache.pkl"
OUT_VECTOR_DB = "deploy_vector_db_cache.pkl"
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]


def load_pdf_docs():
    pdf_files = []
    for folder in PDF_PATHS:
        if not os.path.isdir(folder):
            continue
        pdf_files.extend(glob.glob(os.path.join(folder, "*.pdf")))
    pdf_files = sorted(set(pdf_files))
    docs = []
    for path in pdf_files:
        reader = PdfReader(path)
        filename = os.path.basename(path)
        for page_num, page in enumerate(reader.pages, start=1):
            content = (page.extract_text() or "").strip()
            if content:
                docs.append({"source": filename, "text": content, "page": page_num})
    return docs


def build_chunks_with_metadata(docs):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=250)
    chunks, metadatas = [], []
    for doc in docs:
        text = doc.get("text", "")
        if not text.strip():
            continue
        for chunk in splitter.split_text(text):
            chunks.append(chunk)
            meta = {"source": doc.get("source", "ไม่ระบุ")}
            if doc.get("page"):
                meta["page"] = doc["page"]
            metadatas.append(meta)
    return chunks, metadatas


def main():
    print(f"[1/4] กำลังอ่านไฟล์ PDF จาก {PDF_PATHS} ...")
    docs = load_pdf_docs()
    print(f"      พบ {len(docs)} หน้า")

    print("[2/4] กำลังแบ่ง chunk ...")
    chunks, metadatas = build_chunks_with_metadata(docs)
    print(f"      ได้ {len(chunks)} chunks")

    with open(OUT_CHUNKS, "wb") as f:
        pickle.dump((chunks, metadatas), f)
    print(f"[3/4] เก็บ chunks cache ที่ {OUT_CHUNKS}")

    print(f"[4/4] กำลังสร้าง embeddings ด้วยโมเดล {EMBEDDING_MODEL} (อาจใช้เวลาสักครู่) ...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_db = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)

    with open(OUT_VECTOR_DB, "wb") as f:
        pickle.dump(vector_db, f)
    print(f"      เก็บ vector DB cache ที่ {OUT_VECTOR_DB}")
    print("เสร็จแล้ว! นำไฟล์ทั้งสองไปฝังเข้า Docker image ได้เลย (Dockerfile ทำให้อัตโนมัติ)")


if __name__ == "__main__":
    main()
