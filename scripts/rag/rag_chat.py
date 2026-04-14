# rag_chat.py
# -----------------------------------------------------
# 依賴: pip install openai sentence-transformers faiss-cpu numpy
# 用途: 載入 embeddings/index.faiss + manifest.jsonl -> 檢索 -> 丟給 ChatGPT
# 環境變數: OPENAI_API_KEY（若缺會在啟動時要求輸入）
# 可選環境變數: EMB_DIR (預設 "embeddings")
# -----------------------------------------------------

import os
import json
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
from openai import OpenAI

from bm25_search_local import bm25_search

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ---- 可調參數 ----
EMB_DIR     = os.path.join(PROJECT_ROOT, "data", "embeddings")  # 確保和 rag_build.py 使用的目錄一致
MODEL_NAME  = "BAAI/bge-m3"
CHAT_MODEL  = "gpt-4o-mini"
TOP_K       = 20
SECTION_PRI = ["stats","evolution","moves_learned","moves_machine","gameinfo","pokedex","profile","other"]

# ---- 一次性載入（性能關鍵）----
def _load_manifest(path: str) -> List[Dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))
    return items

def _load_chunk_text(path: str) -> Tuple[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        rec = json.load(f)
    return (rec.get("text") or "").strip(), (rec.get("metadata") or {})

def _init_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        # 只在本機方便測試；正式環境請用環境變數設定
        try:
            key = input("請輸入 OPENAI_API_KEY（不會被保存）：").strip()
        except EOFError:
            key = ""
        if key:
            os.environ["OPENAI_API_KEY"] = key
        else:
            raise RuntimeError("缺少 OPENAI_API_KEY，請設定後再執行。")
    return OpenAI()

# 單例
MODEL    = SentenceTransformer(MODEL_NAME)
INDEX    = faiss.read_index(os.path.join(EMB_DIR, "index.faiss"))
MANIFEST = _load_manifest(os.path.join(EMB_DIR, "manifest.jsonl"))

def retrieve(query: str, *,
             section_filter: Optional[set] = None,
             dex_filter: Optional[set] = None,
             k: int = TOP_K) -> List[Dict[str, Any]]:

    q = MODEL.encode([query], normalize_embeddings=True).astype("float32")

    # 先多抓一些，後面做 metadata 過濾與排序
    K0 = max(k * 4, 20)
    D, I = INDEX.search(q, K0)
    D, I = D[0], I[0]

    hits = []
    for idx, score in zip(I.tolist(), D.tolist()):
        if idx < 0:
            continue
        m = MANIFEST[idx]
        if section_filter and m["section"] not in section_filter:
            continue
        if dex_filter and (m["dex_index"] not in dex_filter):
            continue
        text, md = _load_chunk_text(m["path"])
        hits.append({
            "score": float(score),
            "doc_id": m["id"],
            "section": m["section"],
            "dex_index": m["dex_index"],
            "name": m["name"],
            "path": m["path"],
            "text": text,
            "metadata": md
        })

    # 先按 section 優先級，再按相似度
    pri = {sec: i for i, sec in enumerate(SECTION_PRI)}
    hits.sort(key=lambda x: (pri.get(x["section"], 999), -x["score"]))
    return hits[:k]

def rrf_merge(bm25_hits, vec_hits, k=TOP_K, k_rrf=60):
    pool = {}
    def add(list_hits):
        for rank, h in enumerate(list_hits, 1):
            key = h["doc_id"]
            if key not in pool:
                pool[key] = {"hit": h, "score": 0.0}
            pool[key]["score"] += 1.0 / (k_rrf + rank)
    add(bm25_hits)
    add(vec_hits)
    fused = sorted(pool.values(), key=lambda x: -x["score"])
    return [x["hit"] for x in fused[:k]]


def retrieve_hybrid(query: str, *,
                    section_filter=None,
                    dex_filter=None,
                    k: int = TOP_K):
    vec_hits = retrieve(query, section_filter=section_filter, dex_filter=dex_filter, k=max(k, 12))
    bm_hits  = bm25_search(query, k=max(20, k*2))
    return rrf_merge(bm_hits, vec_hits, k=k)


def build_prompt(query: str, evidences: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    bullet = []
    for ev in evidences:
        name = ev.get("name") or ""
        sec  = ev.get("section")
        did  = ev.get("doc_id")
        txt  = ev.get("text")
        src  = f"{name}｜{sec}｜{did}"
        bullet.append(f"- 來源：{src}\n  摘要：{txt}")

    context = "以下是可用的資料段落（已按相關性排序）：\n" + "\n\n".join(bullet)
    guidelines = (
        "請只根據提供的資料回答；若無資料，請誠實說明「查無資料」。"
        "若問題涉及不同形態或世代，請明確指出。回答最後以『來源』列出使用的 doc_id。"
    )

    return [
        {"role": "system", "content": "你是一位熟悉寶可夢資料的助理。回覆要精簡、準確、引用來源。"},
        {"role": "user", "content": f"{guidelines}\n\n{context}\n\n使用者問題：{query}"}
    ]

def chat_loop():
    client = _init_client()
    print("💬 RAG Chat ready. Ctrl+C 退出。\n")

    while True:
        try:
            q = input("你：").strip()
            if not q:
                continue

            # 簡單 router（可自行加強）
            section_filter = None
            if any(k in q for k in ["種族值","能力值","總和","BS"]):
                section_filter = {"stats"}
            elif any(k in q for k in ["進化","怎麼進化","進化成"]):
                section_filter = {"evolution"}
            elif any(k in q for k in ["學會","教學","等級學會"]):
                section_filter = {"moves_learned", "moves_machine"}
            elif any(k in q for k in ["圖鑑","世代","紅","綠","藍","劍","盾","晶燦","珍珠"]):
                section_filter = {"pokedex"}
            elif any(k in q for k in ["身高","體重","分類","特性","屬性","蛋群","性別","捕獲","首登場"]):
                section_filter = {"gameinfo"}
            elif any(k in q for k in ["簡介","外觀","介紹"]):
                section_filter = {"profile"}

            evidences = retrieve_hybrid(q, section_filter=section_filter, k=TOP_K)
            messages = build_prompt(q, evidences)

            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.2,
            )
            ans = resp.choices[0].message.content

            sources = ", ".join([e["doc_id"] for e in evidences[:min(5, len(evidences))]])
            print(f"\n助理：{ans}\n\n（來源：{sources}）\n")

        except KeyboardInterrupt:
            print("\n👋 再見！")
            break

if __name__ == "__main__":
    chat_loop()
