# bm25_build_local.py
import os, json, re
from rank_bm25 import BM25Okapi
from tqdm import tqdm

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
EMB_DIR = os.path.join(PROJECT_ROOT, "data", "embeddings")

def load_manifest():
    with open(os.path.join(EMB_DIR, "manifest.jsonl"), "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def tokenize(text):
    # 你可以改成 jieba.cut()，這裡先簡化成空白與符號切割
    return re.findall(r"[\w一-龥]+", text)

def build_bm25():
    manifest = load_manifest()
    corpus = []
    ids = []

    for m in tqdm(manifest, desc="Preparing corpus"):
        path = m["path"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
            text = (rec.get("text") or "").strip()
            corpus.append(tokenize(text))
            ids.append(m)
        except Exception as e:
            print("Skip", path, e)

    print("Building BM25 index...")
    bm25 = BM25Okapi(corpus)

    import pickle
    with open(os.path.join(EMB_DIR, "bm25.pkl"), "wb") as f:
        pickle.dump({"bm25": bm25, "manifest": ids}, f)

    print("✅ Done, saved to data/embeddings/bm25.pkl")

if __name__ == "__main__":
    build_bm25()
