# bm25_search_local.py
import os, json, pickle, re
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
EMB_DIR = os.path.join(PROJECT_ROOT, "data", "embeddings")

def tokenize(text):
    return re.findall(r"[\w一-龥]+", text)

with open(os.path.join(EMB_DIR, "bm25.pkl"), "rb") as f:
    data = pickle.load(f)
BM25 = data["bm25"]
MANIFEST = data["manifest"]

def bm25_search(query: str, k: int = 10) -> List[Dict[str, Any]]:
    tokens = tokenize(query)
    scores = BM25.get_scores(tokens)
    ranked = sorted(zip(MANIFEST, scores), key=lambda x: -x[1])[:k]
    out = []
    for m, s in ranked:
        try:
            with open(m["path"], "r", encoding="utf-8") as f:
                rec = json.load(f)
            out.append({
                "score": float(s),
                "doc_id": m["id"],
                "section": m["section"],
                "dex_index": m["dex_index"],
                "name": m["name"],
                "path": m["path"],
                "text": rec.get("text", ""),
            })
        except:
            continue
    return out
