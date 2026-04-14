# rag_build.py
# --------------------------------------------
# 需求: pip install sentence-transformers faiss-cpu numpy tqdm
# 用途: 掃描 data/chunk 下所有 json 檔 -> 產生向量 -> 存 embeddings/
# --------------------------------------------

import os
import json
import glob
import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import faiss

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHUNK_ROOT = os.path.join(PROJECT_ROOT, "data", "chunk")   # 你的 chunk 目錄
EMB_DIR    = os.path.join(PROJECT_ROOT, "data", "embeddings")   # 輸出資料夾
MODEL_NAME = "BAAI/bge-m3"  # 或 "intfloat/multilingual-e5-large"
BATCH_SIZE = 128
HNSW_M     = 32             # HNSW 圖的度數，越大查準率越高

os.makedirs(EMB_DIR, exist_ok=True)

def iter_chunk_files(root: str):
    pattern = os.path.join(root, "**", "*.json")
    yield from glob.iglob(pattern, recursive=True)

def load_record(path: str):
    with open(path, "r", encoding="utf-8") as f:
        rec = json.load(f)
    # 防呆 + 最小欄位
    return {
        "id": rec.get("doc_id") or os.path.basename(path),
        "path": path,
        "section": rec.get("section") or "unknown",
        "text": (rec.get("text") or "").strip(),
        "dex_index": (rec.get("metadata", {}) or {}).get("dex_index"),
        "name": (rec.get("metadata", {}) or {}).get("name"),
    }

def batchify(items, bs):
    buf = []
    for x in items:
        buf.append(x)
        if len(buf) >= bs:
            yield buf
            buf = []
    if buf:
        yield buf

def main():
    files = list(iter_chunk_files(CHUNK_ROOT))
    print(f"📦 Found {len(files)} chunk files under {CHUNK_ROOT}")

    model = SentenceTransformer(MODEL_NAME)
    normalize = True

    manifest = []
    all_vecs = []
    offset = 0

    for batch_paths in tqdm(list(batchify(files, BATCH_SIZE)), desc="Embedding"):
        batch = [load_record(p) for p in batch_paths]
        texts = [b["text"] for b in batch]
        vecs = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=False, normalize_embeddings=normalize)
        all_vecs.append(vecs)

        for b in batch:
            manifest.append({
                "id": b["id"],
                "path": b["path"],
                "section": b["section"],
                "dex_index": b["dex_index"],
                "name": b["name"],
                "offset": offset
            })
            offset += 1

    # 保存向量矩陣
    mat = np.vstack(all_vecs) if all_vecs else np.zeros((0, 768), dtype="float32")
    np.save(os.path.join(EMB_DIR, "vecs.npy"), mat)

    # 保存 manifest.jsonl
    with open(os.path.join(EMB_DIR, "manifest.jsonl"), "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 建 FAISS 索引（HNSW）
    dim = mat.shape[1] if mat.size else 768
    index = faiss.IndexHNSWFlat(dim, HNSW_M)
    if mat.size:
        index.hnsw.efConstruction = 100
        index.add(mat.astype("float32"))
    faiss.write_index(index, os.path.join(EMB_DIR, "index.faiss"))

    print("✅ Done.\n - embeddings/vecs.npy\n - embeddings/manifest.jsonl\n - embeddings/index.faiss")

if __name__ == "__main__":
    main()
