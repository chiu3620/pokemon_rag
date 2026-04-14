# rag_chat_hybrid.py
# -----------------------------------------------------
# 依賴: pip install openai sentence-transformers faiss-cpu numpy rank-bm25
# 用途: 載入 embeddings/index.faiss + manifest.jsonl -> 執行混合檢索 (Vector + BM25) -> Rerank -> 丟給 ChatGPT
# 環境變數: OPENAI_API_KEY（若缺會在啟動時要求輸入）
# 可選環境變數: EMB_DIR (預設 "embeddings")
# -----------------------------------------------------

import os
import json
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ---- 可調參數 ----
EMB_DIR         = os.environ.get("EMB_DIR", os.path.join(PROJECT_ROOT, "data", "embeddings")) # 確保和 rag_build.py 使用的目錄一致
MODEL_NAME      = "BAAI/bge-m3"                          # 用於 Dense Retrieval
RERANK_MODEL    = "BAAI/bge-reranker-large"              # 用於 Rerank
CHAT_MODEL      = "gpt-4o-mini"
TOP_K_DENSE     = 10 # Dense Retrieval 要撈回的數量
TOP_K_SPARSE    = 10 # Sparse Retrieval (BM25) 要撈回的數量
TOP_K_FINAL     = 5  # Rerank 後最終保留的數量

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
    # 延遲 import，因為不是所有情境都需要 OpenAI
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        try:
            key = input("請輸入 OPENAI_API_KEY（不會被保存）：").strip()
        except EOFError:
            key = ""
        if key:
            os.environ["OPENAI_API_KEY"] = key
        else:
            raise RuntimeError("缺少 OPENAI_API_KEY，請設定後再執行。")
    return OpenAI()

def _init_bm25(manifest: List[Dict[str, Any]]) -> Tuple[BM25Okapi, Dict[str, str]]:
    """ 載入所有文件內容並初始化 BM25 """
    print("正在初始化 BM25 Index...")
    corpus_map = {}
    corpus_texts = []
    for m in manifest:
        text, _ = _load_chunk_text(m["path"])
        corpus_map[m["id"]] = text
        corpus_texts.append(text)
    
    # BM25 需要分詞後的語料庫，這裡簡單用空白切割
    tokenized_corpus = [doc.split(" ") for doc in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    print("BM25 Index 初始化完成。")
    return bm25, corpus_map

# ---- 全域單例（避免重複載入）----
print("正在載入模型和索引...")
# 用於 Dense Retrieval 的 Bi-Encoder
BI_ENCODER = SentenceTransformer(MODEL_NAME)
# 用於 Rerank 的 Cross-Encoder
CROSS_ENCODER = CrossEncoder(RERANK_MODEL)

INDEX    = faiss.read_index(os.path.join(EMB_DIR, "index.faiss"))
MANIFEST = _load_manifest(os.path.join(EMB_DIR, "manifest.jsonl"))

# 初始化 BM25
BM25_INDEX, CORPUS_MAP = _init_bm25(MANIFEST)
print("模型和索引載入完成。")


def retrieve(query: str, *,
             section_filter: Optional[set] = None,
             dex_filter: Optional[set] = None,
             k_dense: int = TOP_K_DENSE,
             k_sparse: int = TOP_K_SPARSE,
             k_final: int = TOP_K_FINAL) -> List[Dict[str, Any]]:

    # === 步驟 1: Dense Retrieval (Vector Search) ===
    q_emb = BI_ENCODER.encode([query], normalize_embeddings=True).astype("float32")
    D, I = INDEX.search(q_emb, k_dense)
    dense_hits = []
    for idx, score in zip(I[0].tolist(), D[0].tolist()):
        if idx >= 0:
            dense_hits.append({"manifest": MANIFEST[idx], "score": float(score)})
            
    # === 步驟 2: Sparse Retrieval (BM25) ===
    tokenized_query = query.split(" ")
    bm25_scores = BM25_INDEX.get_scores(tokenized_query)
    top_n_indices = np.argsort(bm25_scores)[::-1][:k_sparse]
    sparse_hits = []
    for idx in top_n_indices:
        # BM25 分數通常大於 0，這裡簡單給一個 score，主要用於合併
        sparse_hits.append({"manifest": MANIFEST[idx], "score": bm25_scores[idx]})

    # === 步驟 3: Fusion (合併與去重) ===
    combined_hits = {}
    for hit in dense_hits + sparse_hits:
        doc_id = hit["manifest"]["id"]
        if doc_id not in combined_hits:
            combined_hits[doc_id] = hit["manifest"]
            
    candidates_manifest = list(combined_hits.values())

    # 過濾 metadata
    if section_filter or dex_filter:
        filtered_candidates = []
        for m in candidates_manifest:
            if section_filter and m["section"] not in section_filter:
                continue
            if dex_filter and (m["dex_index"] not in dex_filter):
                continue
            filtered_candidates.append(m)
        candidates_manifest = filtered_candidates

    if not candidates_manifest:
        return []

    # === 步驟 4: Reranking ===
    # 準備 reranker 的輸入格式： (query, document_text)
    rerank_pairs = []
    for m in candidates_manifest:
        doc_text = CORPUS_MAP.get(m["id"], "")
        rerank_pairs.append([query, doc_text])

    # 取得 rerank 分數
    rerank_scores = CROSS_ENCODER.predict(rerank_pairs)

    # 將分數加回 manifest 並建立最終結果
    final_hits = []
    for m, score in zip(candidates_manifest, rerank_scores):
        text, md = _load_chunk_text(m["path"])
        final_hits.append({
            "score": float(score), # 現在的分數是 rerank score
            "doc_id": m["id"],
            "section": m["section"],
            "dex_index": m["dex_index"],
            "name": m["name"],
            "path": m["path"],
            "text": text,
            "metadata": md
        })

    # === 步驟 5: 排序並返回 Top K ===
    # 按 rerank 分數從高到低排序
    final_hits.sort(key=lambda x: x["score"], reverse=True)
    
    return final_hits[:k_final]


def build_prompt(query: str, evidences: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    bullet = []
    for ev in evidences:
        name = ev.get("name") or ""
        sec  = ev.get("section")
        did  = ev.get("doc_id")
        txt  = ev.get("text")
        src  = f"{name}｜{sec}｜{did}"
        bullet.append(f"- 來源：{src}\n  摘要：{txt}")

    if not bullet:
        context = "沒有找到相關資料。"
    else:
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
    print("\n💬 RAG Chat (Hybrid Search + Rerank) is ready. Ctrl+C 退出。\n")

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
                section_filter = {"gameinfo", "profile"} # 合併相似類別

            evidences = retrieve(q, section_filter=section_filter) # k 參數使用預設值
            messages = build_prompt(q, evidences)

            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.2,
            )
            ans = resp.choices[0].message.content

            used_sources = ", ".join([e["doc_id"] for e in evidences])
            print(f"\n助理：{ans}\n\n（來源：{used_sources}）\n")

        except KeyboardInterrupt:
            print("\n👋 再見！")
            break
        except Exception as e:
            print(f"\n發生錯誤：{e}")
            break

if __name__ == "__main__":
    chat_loop()
