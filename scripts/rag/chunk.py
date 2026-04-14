import os
import json
import re
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter, defaultdict

# 1. 整理共用 metadata
def _normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00A0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def _latin_only_or_none(s: Optional[str]) -> Optional[str]:
    _LATIN_RE = re.compile(r"[A-Za-zÀ-ÿ'`\-\. ]+")
    if not isinstance(s, str):
        return None
    s = _normalize_spaces(s)
    parts = _LATIN_RE.findall(s)
    out = " ".join(p.strip() for p in parts).strip()
    return out or None


def normalize_metadata(raw: Dict[str, Any], output_root: str, image_root: str) -> Dict[str, Any]:
    """
    整理每隻寶可夢的共用 metadata 並輸出：
    - 從 raw["name"] 取出名稱
    - 從 raw["names"] 取出各國的名稱
    - 從 raw["index"] 取出圖鑑編號
    - 從 raw["generation"] 取出世代
    - 從 raw["forms"][0]["image"] 取出圖片位置
    - 從 raw["source_url"] 取出來源網址
    - 儲存到 data/chunk/metadata/XXXX-metadata.json
    """
    # === 1. 取得基本欄位 ===
    dex_raw = str(raw["index"])
    dex_digits = re.sub(r"\D", "", dex_raw)
    dex_index = dex_digits.zfill(4)
    index_int = int(dex_digits)

    gen_map = {
        "第一世代": 1, "第二世代": 2, "第三世代": 3, "第四世代": 4,
        "第五世代": 5, "第六世代": 6, "第七世代": 7, "第八世代": 8, "第九世代": 9
    }
    gen_clean = gen_map.get(_normalize_spaces(raw.get("generation", "")), None)

    # === 2. 名稱處理 ===
    names_in = dict(raw.get("names", {}))
    if "name_en" in raw: names_in.setdefault("en", raw["name_en"])
    if "name_jp" in raw: names_in.setdefault("ja", raw["name_jp"])

    LANG_KEYS = ["zh_hant", "zh_hans", "ja", "en", "es", "fr", "de", "it", "ko"]
    names = {}
    for key in LANG_KEYS:
        val = names_in.get(key)
        if isinstance(val, str):
            val = _normalize_spaces(val)
            if key in {"en", "fr", "de", "it", "es"}:
                val = _latin_only_or_none(val)
            names[key] = val or None
        else:
            names[key] = None

    name_primary = raw.get("name") or names.get("zh_hant") or names.get("zh_hans") or names.get("en")
    name_primary = _normalize_spaces(name_primary)
    if not names.get("zh_hant"):
        names["zh_hant"] = name_primary

    aliases = sorted({n for n in names.values() if n}, key=lambda x: (len(x), x))

    # === 3. 圖片（從 forms 中找） ===
    image = None
    if isinstance(raw.get("forms"), list) and len(raw["forms"]) > 0:
        form = raw["forms"][0]
        image = form.get("image")
        if isinstance(image, str) and image and not image.startswith(("http://", "https://", "/")):
            image = image_root.rstrip("/") + "/" + image

    # === 4. 組裝 metadata ===
    meta = {
        "dex_index": dex_index,
        "index": index_int,
        "gen": gen_clean,
        "name": name_primary,
        "names": names,
        "aliases": aliases,
        "image_path": image,
        "source_url": raw.get("source_url"),
        "last_retrieved": raw.get("last_retrieved"),
    }
    meta = {k: v for k, v in meta.items() if v is not None}

    # === 5. 輸出檔案 ===
    meta_dir = os.path.join(output_root, "metadata")
    os.makedirs(meta_dir, exist_ok=True)
    output_path = os.path.join(meta_dir, f"{dex_index}-metadata.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta


# 2. 整理 profile 的content
def _chunk_text_by_newline(text: str, max_chars: int = 500, min_chars: int = 200):
    """
    用換行符切段（自動支援一行或多行換行），再依字數切小段。
    """
    # 先清理空白
    text = (text or "").strip()
    if not text:
        return []

    # 🔹 用 re.split(r"\n+") 切開（支援一個或多個換行）
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks = []

    for p in paragraphs:
        # 段落長度剛好或偏短 → 直接收
        if len(p) <= max_chars:
            chunks.append(p)
            continue

        # 段落太長 → 再用句號切開重組
        sents = [s.strip() for s in re.split(r"(?<=[。！？!?])", p) if s.strip()]
        buf, cur_len = [], 0
        for s in sents:
            if cur_len + len(s) > max_chars and cur_len >= min_chars:
                chunks.append("".join(buf).strip())
                buf, cur_len = [s], len(s)
            else:
                buf.append(s)
                cur_len += len(s)
        if buf:
            chunks.append("".join(buf).strip())

    return chunks


def build_profile_chunks(raw: dict, meta: dict, output_root: str, max_chars: int = 500) -> list[str]:
    """
    從 raw["profile"] 生成多個 chunk，輸出到 data/chunk/profile/XXXX-profile-001.json ...
    每個 chunk 一筆 json，包含完整 metadata。
    """
    dex = meta["dex_index"]
    profile_text = (raw.get("profile") or "").strip()

    out_dir = os.path.join(output_root, "profile")
    os.makedirs(out_dir, exist_ok=True)

    if not profile_text:
        print(f"⚠️ {dex} 沒有 profile 內容")
        return []

    # 切割成多段文字（每段 <= max_chars）
    chunks = _chunk_text_by_newline(profile_text, max_chars=max_chars)

    out_paths = []
    for i, text in enumerate(chunks, start=1):
        record = {
            "doc_id": f"pokemon-{dex}-profile-{i:03d}",
            "section": "profile",
            "text": text,
            "metadata": meta
        }

        out_path = os.path.join(out_dir, f"{dex}-profile-{i:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    print(f"✅ 已建立 {len(out_paths)} 個 profile chunks → {dex}")
    return out_paths


# 3. 整理 進化鏈 的content
def build_evolution_chunk(raw: dict, meta: dict, output_root: str,) -> str:
    """
    從 raw["evolution_chains"] 產生單一演化描述檔：
      data/chunk/evolution/{dex}-evolution.json

    規則：
    - 每條演化鏈 (chain) 內，對每個有 `from` 的節點輸出「A 方法 進化為 B」
    - 若該鏈只有單節點，輸出「X 沒有進化形態」
    - 多條演化鏈以「；」分隔（你也可以改成 "，"）
    - 最前面加上前綴「進化鏈：」
    """
    dex = meta["dex_index"]
    chains = raw.get("evolution_chains") or []

    out_dir = os.path.join(output_root, "evolution")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{dex}-evolution-001.json")

    chain_texts = []

    if not chains:
        record = {
            "doc_id": f"pokemon-{dex}-evolution-001",
            "section": "evolution",
            "text": "進化鏈：資料缺失",
            "metadata": {**meta}
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return out_path

    for chain in chains:
        if not isinstance(chain, list) or not chain:
            continue

        # 單節點：不進化
        if len(chain) == 1:
            name = (chain[0].get("name") or "").strip()
            chain_texts.append(f"{name} 沒有進化形態")
            continue

        # 多節點：蒐集所有 from->to 的步驟
        steps = []
        for node in chain:
            to_name = (node.get("name") or "").strip()
            from_name = (node.get("from") or "").strip()
            method = (node.get("text") or node.get("back_text") or "").strip()

            if not from_name:
                continue  # 起點不輸出

            if method:
                step_text = f"{from_name} {method} 進化為 {to_name}"
            else:
                step_text = f"{from_name} 進化為 {to_name}"

            steps.append(step_text)

        if steps:
            # 你想用「；」分隔每個步驟
            chain_texts.append("；".join(steps))

    final_text = "進化鏈：" + "；".join(chain_texts) if chain_texts else "進化鏈：資料缺失"

    record = {
        "doc_id": f"pokemon-{dex}-evolution-001",
        "section": "evolution",
        "text": final_text,
        "metadata": {**meta}  # 用展開確保這份是副本
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return out_path


# 4. 整理 遊戲相關資訊 的content
def _natural_join(items):
    items = [s for s in items if isinstance(s, str) and s.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]}和{items[1]}"
    return "、".join(items)

def _types_text(types):
    types = [t for t in (types or []) if t]
    if len(types) == 2:
        return f"{types[0]}跟{types[1]}"
    return types[0] if types else ""

def detect_form_intro(name: str, form: dict, species_gen: int | None):
    """
    回傳 (region_name_or_None, intro_gen)
    規則優先度：Mega/Gmax > 地區名稱 > 物種世代
    """
    _REGION_RULES = [
        ("阿羅拉", 7, re.compile(r"阿羅拉")),
        ("伽勒爾", 8, re.compile(r"伽勒爾")),
        ("洗翠",   8, re.compile(r"洗翠")),
        ("帕底亞", 9, re.compile(r"帕底亞")),
    ]
    # 特殊形態旗標
    if form.get("is_mega"):
        return (None, 6)
    if form.get("is_gmax"):
        return (None, 8)

    # 地區形態（從名稱判斷）
    for region, gen, pat in _REGION_RULES:
        if pat.search(name or ""):
            return (region, gen)

    # 預設回物種世代（保持相容）
    return (None, species_gen)


def build_gameinfo_chunks(raw: dict, meta: dict, output_root: str) -> list[str]:
    """
    從 raw['forms'] 產生『遊戲相關資訊』，每個型態輸出一份 JSON：
      data/chunk/gameinfo/{dex}-gameinfo-{form_index}.json

    重點：
      - 名稱後自動加上（地區形態）標註（若有）
      - 世代使用「形態首登場世代」而非物種世代
      - metadata 同時包含：
          * 當前 form 的完整資料（form）
          * 全部 forms 清單（forms）
          * form_intro_gen / form_region
    """
    dex = meta["dex_index"]
    species_gen = meta.get("gen")          # 物種初登場世代（例如 急凍鳥=1）
    forms = raw.get("forms") or []

    out_dir = os.path.join(output_root, "gameinfo")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: list[str] = []
    for i, form in enumerate(forms, start=1):
        form_name = (form.get("name", "") or meta.get("name", "")).strip()

        # 🔹偵測此形態的首登場世代與地區
        region, intro_gen = detect_form_intro(form_name, form, species_gen)
        gen_text = f"第{intro_gen}世代" if intro_gen else ""
        name_with_region = f"{form_name}（{region}形態）" if region else form_name

        # 屬性
        types = form.get("types") or []
        types_str = _types_text(types)

        # 分類
        genus = (form.get("genus") or "").strip()

        # 特性 / 隱藏特性
        abilities = form.get("ability") or []
        normal_abilities = [a["name"] for a in abilities if not a.get("is_hidden")]
        hidden_abilities = [a["name"] for a in abilities if a.get("is_hidden")]
        normal_abilities_str = "、".join(normal_abilities) if normal_abilities else ""
        hidden_abilities_str = "、".join(hidden_abilities) if hidden_abilities else ""

        # 經驗、速度
        exp = form.get("experience") or {}
        exp_number = exp.get("number")
        exp_speed = exp.get("speed")

        # 身高 / 體重
        height = form.get("height") or ""
        weight = form.get("weight") or ""

        # 性別比例
        gender = form.get("gender_rate") or {}
        male = gender.get("male")
        female = gender.get("female")

        # 蛋群
        egg_groups = form.get("egg_groups") or []
        egg_groups_str = _natural_join(egg_groups)

        # 捕獲率
        catch = form.get("catch_rate") or {}
        catch_num = catch.get("number")
        catch_rate = catch.get("rate")

        # ---- 拼句 ----
        parts = []
        head = [name_with_region]
        if gen_text:
            head.append(gen_text)
        head.append(f"全國圖鑑編號是{dex}")
        parts.append("，".join(head))

        if types_str:
            parts.append(f"屬性是{types_str}")
        if genus:
            parts.append(f"分類是{genus}")
        if normal_abilities_str:
            parts.append(f"特性是{normal_abilities_str}")
        if hidden_abilities_str:
            parts.append(f"隱藏特性是{hidden_abilities_str}")
        if height:
            parts.append(f"身高是{height}")
        if weight:
            parts.append(f"體重是{weight}")
        if male or female:
            segs = []
            if male: segs.append(f"公{male}")
            if female: segs.append(f"母{female}")
            parts.append(f"性別比例是{'、'.join(segs)}")
        if egg_groups_str:
            parts.append(f"蛋群是{egg_groups_str}")
        if exp_number:
            parts.append(f"升級所需經驗是{exp_number}")
        if exp_speed:
            parts.append(f"升級速度{exp_speed}")
        if catch_num or catch_rate:
            tail = f"{catch_num or ''}"
            if catch_rate:
                tail += f"（{catch_rate}）"
            parts.append(f"捕獲率是{tail}")

        text = "，".join(parts).rstrip("，") + "。"

        record = {
            "doc_id": f"pokemon-{dex}-gameinfo-{i:03d}",
            "section": "gameinfo",
            "text": text,
            "metadata": {
                **meta,
                "form_intro_gen": intro_gen,   # 形態首登場世代
                "form_region": region,         # 地區（若有）
                "form": form,                  # 當前型態完整資料
            }
        }

        out_path = os.path.join(out_dir, f"{dex}-gameinfo-{i:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    # 若沒有 forms，也輸出占位檔
    if not out_paths:
        placeholder = {
            "doc_id": f"pokemon-{dex}-gameinfo-001",
            "section": "gameinfo",
            "text": "遊戲資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-gameinfo-001.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)


    return out_paths

# 5. 整理 總種族 的content
# --- helpers ---
def _to_int(x):
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    s = str(x).strip().replace(",", "")
    m = re.match(r"^-?\d+$", s)
    return int(s) if m else 0

def _extract_region_from_text(t: str) -> str | None:
    if not t:
        return None
    for kw in _REGION_KEYWORDS:
        if kw in t:
            return kw
    return None

def _ensure_species_in_label(form_label: str, species_name: str) -> str:
    """
    若 form_label 沒包含物種名，補上『物種名 空格 form_label』
    例：
      - '伽勒爾的樣子' → '急凍鳥 伽勒爾的樣子'
      - '一般' → '急凍鳥 一般'
      - '普通伊布'（已含『伊布』）→ 保持原樣
    """
    label = (form_label or "").strip()
    sp = (species_name or "").strip()
    if not label:
        return sp  # 空就直接用物種名
    if sp and sp not in label:
        return f"{sp} {label}"
    return label


# --- main ---
def build_stats_chunks(raw: dict, meta: dict, output_root: str) -> list[str]:
    """
    從 raw['stats'] 產生『總種族值』內容；每個 stats 項輸出一份 JSON：
      data/chunk/stats/{dex}-stats-001.json, 002.json, ...
    規則：
      - 偵測地區型態關鍵字（阿羅拉／伽勒爾／洗翠／帕底亞），寫進 metadata.stats.form_region
      - 若 form 標籤沒含物種名，會補上（例如 '一般' → '急凍鳥 一般'）
      - 文字格式如：『急凍鳥 伽勒爾的樣子 的種族值是HP ...，總種族值 ...。』
    """
    dex = meta["dex_index"]
    species_name = meta.get("name") or ""
    stats_list = raw.get("stats") or []

    out_dir = os.path.join(output_root, "stats")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: list[str] = []
    if not stats_list:
        placeholder = {
            "doc_id": f"pokemon-{dex}-stats",
            "section": "stats",
            "text": "種族值資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-stats.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        return [out_path]

    for i, item in enumerate(stats_list, start=1):
        form_label_raw = (item.get("form") or "").strip()
        # 若沒有物種名，補上
        form_label = _ensure_species_in_label(form_label_raw, species_name)

        # 地區偵測（從 form 標籤中抓）
        region = _extract_region_from_text(form_label)

        data = item.get("data") or {}
        hp  = _to_int(data.get("hp"))
        atk = _to_int(data.get("attack"))
        de  = _to_int(data.get("defense"))
        spa = _to_int(data.get("sp_attack"))
        spd = _to_int(data.get("sp_defense"))
        spe = _to_int(data.get("speed"))
        total = hp + atk + de + spa + spd + spe

        text = (
            f"{form_label} 的種族值是"
            f"HP {hp}／攻擊 {atk}／防禦 {de}／特攻 {spa}／特防 {spd}／速度 {spe}，"
            f"總種族值 {total}。"
        )

        record = {
            "doc_id": f"pokemon-{dex}-stats-{i:03d}",
            "section": "stats",
            "text": text,
            "metadata": {
                **meta,
                "stats": {
                    "form": form_label,           # 已補上物種名的標籤
                    "form_region": region,        # 若能偵測到『阿羅拉／伽勒爾／洗翠／帕底亞』
                    "values": {
                        "hp": hp,
                        "attack": atk,
                        "defense": de,
                        "sp_attack": spa,
                        "sp_defense": spd,
                        "speed": spe,
                        "total": total
                    }
                }
            }
        }

        out_path = os.path.join(out_dir, f"{dex}-stats-{i:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    return out_paths

# 6. 整理 圖鑑的介紹 的content
# ---- Helpers ----


def _clean_pokedex_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\u00A0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip("＊*")

def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _display_label(group: str, version: str) -> str:
    """
    生成『寶可夢 金』、『寶可夢 銀』……
    修正：group 含「／」時，抓系列前綴（第一個非空白 token），再接版本名。
    """
    group = _normalize_space(group)
    version = _normalize_space(version)

    if "／" in group and version:
        # 例：'寶可夢 金／銀'、'寶可夢 劍／盾'、'精靈寶可夢 Let's Go！皮卡丘／Let's Go！伊布'
        first_seg = group.split("／", 1)[0]           # '寶可夢 金' / '精靈寶可夢 Let's Go！皮卡丘'
        series_prefix = re.split(r"\s+", first_seg)[0] # '寶可夢' / '精靈寶可夢'
        return f"{series_prefix} {version}"

    # group 不含「／」且尾段剛好等於版本名 → 直接回 group（如：'寶可夢 皮卡丘'）
    if group and version and group.endswith(version):
        return group

    if group and version:
        return f"{group} {version}"
    return group or version

def _form_aliases(base_name: str, regions: List[str]) -> List[str]:
    out = []
    for r in regions:
        out.extend([f"{r}{base_name}", f"{base_name}（{r}）", f"{r}形態{base_name}"])
    # 去重
    seen, dedup = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x); dedup.append(x)
    return dedup


# ---- Main builder ----
def build_pokedex_chunks(
    raw: Dict[str, Any],
    meta: Dict[str, Any],
    output_root: str,
    mode: str = "by_gen",  # "by_gen" | "by_version"
) -> List[str]:
    """
    圖鑑介紹（flavor_texts）：
    - by_gen: 每個世代一份 JSON（推薦；符合你指定的句型）
    - by_version: 每個版本一份 JSON（更細）
    自動偵測地區形態（阿羅拉/伽勒爾/洗翠/帕底亞），並在標題加上「/ {地區別名}」。
    版本前綴顯示符合你的例子（寶可夢 紅、寶可夢 皮卡丘、寶可夢 劍…）。
    """
    dex = meta["dex_index"]
    base_name = meta.get("name", "")
    entries = (raw.get("flavor_texts")
               or raw.get("pokedex")
               or raw.get("pokedex_entries")
               or [])

    out_dir = os.path.join(output_root, "pokedex")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: List[str] = []
    if not entries:
        record = {
            "doc_id": f"pokemon-{dex}-pokedex",
            "section": "pokedex",
            "text": "圖鑑介紹資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-pokedex.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return [out_path]

    if mode == "by_version":
        # 每個版本一份
        seq = 1
        for gen_block in entries:
            gen_name = str(gen_block.get("name", "")).strip()  # 例如 "第一世代"
            versions = gen_block.get("versions") or []
            for v in versions:
                v_name  = str(v.get("name", "")).strip()
                v_group = str(v.get("group", "")).strip()
                v_text  = _clean_pokedex_text(v.get("text", ""))

                region = _extract_region_from_text(v_text)
                label = _display_label(v_group, v_name)
                # 標題：『第N世代 基本名 / 基本名 地區  圖鑑介紹：』
                title_names = [base_name]
                if region:
                    title_names.append(f"{base_name} {region}")
                title = f"{gen_name} {' / '.join(title_names)} 圖鑑介紹".strip()

                display = f"{title}：{label}：{v_text}".rstrip("，；。") + "。"

                aliases = meta.get("aliases", [])
                if region:
                    aliases = list({*aliases, *_form_aliases(base_name, [region])})

                record = {
                    "doc_id": f"pokemon-{dex}-pokedex-{seq:03d}",
                    "section": "pokedex",
                    "text": display,
                    "metadata": {
                        **meta,
                        "aliases": aliases,
                        "pokedex_mode": "by_version",
                        "pokedex_generation": gen_name,
                        "pokedex_version": {"name": v_name, "group": v_group},
                        "form_region": region
                    }
                }
                out_path = os.path.join(out_dir, f"{dex}-pokedex-{seq:03d}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
                out_paths.append(out_path)
                seq += 1

        return out_paths

    # ---- by_gen（每世代一份），符合你的句型 ----
    seq = 1
    for gen_block in entries:
        gen_name = str(gen_block.get("name", "")).strip()  # "第一世代"
        versions = gen_block.get("versions") or []
        if not versions:
            # 這個世代沒有資料就跳過（不產生空檔）
            continue

        version_bits, versions_meta, regions_found = [], [], []

        for v in versions:
            v_name  = str(v.get("name", "")).strip()
            v_group = str(v.get("group", "")).strip()
            v_text  = _clean_pokedex_text(v.get("text", ""))

            region = _extract_region_from_text(v_text)
            if region and region not in regions_found:
                regions_found.append(region)

            label = _display_label(v_group, v_name)  # 例如：寶可夢 紅、寶可夢 皮卡丘、寶可夢 劍
            bit = f"{label}：{v_text}".rstrip("，；。") + "。"
            version_bits.append(bit)

            versions_meta.append({
                "name": v_name, "group": v_group, "text": v_text, "form_region": region
            })

        # 標題：『第N世代 名稱 / 名稱 地區  圖鑑介紹：』
        title_names = [base_name] + [f"{base_name} {r}" for r in regions_found]
        title = f"{gen_name} {' / '.join(title_names)} 圖鑑介紹".strip()
        text = f"{title}：" + "；".join(version_bits)

        # 別名擴充（若偵測到地區）
        aliases = meta.get("aliases", [])
        if regions_found:
            aliases = list({*aliases, *_form_aliases(base_name, regions_found)})

        record = {
            "doc_id": f"pokemon-{dex}-pokedex-{seq:03d}",
            "section": "pokedex",
            "text": text,
            "metadata": {
                **meta,
                "aliases": aliases,
                "pokedex_mode": "by_gen",
                "pokedex_generation": gen_name,
                "pokedex_versions": versions_meta,
                "form_regions": regions_found
            }
        }

        out_path = os.path.join(out_dir, f"{dex}-pokedex-{seq:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)
        seq += 1

    # 如果某隻在所有世代都沒有資料（極少見），就輸出占位；否則回傳實際生成的清單
    if not out_paths:
        record = {
            "doc_id": f"pokemon-{dex}-pokedex",
            "section": "pokedex",
            "text": "圖鑑介紹資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-pokedex.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return [out_path]

    return out_paths



# 7. 整理 可以學會的招式 的content
# ---- helpers（若已定義可略） ----
_REGION_KEYWORDS = ["阿羅拉", "伽勒爾", "洗翠", "帕底亞"]

# ---- moves: learned ----
def build_moves_learned_chunks(raw: Dict[str, Any], meta: Dict[str, Any], output_root: str) -> List[str]:
    """
    每個形態輸出一份 JSON：
      data/chunk/moves/learned/{dex}-moves-learned-001.json, 002.json, ...
    文案範例：
      「急凍鳥 一般，進化時學會空氣之刃…；透過招式教學狂學會抓…；提升到12等時學會龍息…」
    規則：
      - level 是數字 → 提升到X等時學會{name}
      - level 是 "—"  → 透過招式教學狂學會（歸到 tutor 類）
      - method 含「進化」 → 進化時學會（優先生效）
    """
    dex = meta["dex_index"]
    species_name = meta.get("name") or ""
    moves = raw.get("moves") or {}
    learned_blocks = moves.get("learned") or []

    out_dir = os.path.join(output_root, "moves")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: List[str] = []
    if not learned_blocks:
        # 沒有任何形態的 learned，也輸出一份占位
        placeholder = {
            "doc_id": f"pokemon-{dex}-moves-learned-001",
            "section": "moves_learned",
            "text": "學習招式（提升等級／教學）資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-moves-learned-001.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        return [out_path]

    for i, block in enumerate(learned_blocks, start=1):
        form_label_raw = (block.get("form") or "").strip()
        form_label = _ensure_species_in_label(form_label_raw, species_name)
        region = _extract_region_from_text(form_label)

        # 分三類蒐集
        evo_moves: List[str] = []
        tutor_moves: List[str] = []
        level_moves: List[str] = []

        data_list = block.get("data") or []
        for m in data_list:
            name = (m.get("name") or "").strip()
            level = (m.get("level_learned_at") or "").strip()
            method = (m.get("method") or "").strip()

            # 進化優先
            if "進化" in level or "進化" in method:
                if name:
                    evo_moves.append(name)
                continue

            # "—" 視為招式教學狂（照你的規則）
            if level == "—":
                if name:
                    tutor_moves.append(name)
                continue

            # 數字等級
            if re.fullmatch(r"\d+", level):
                level_moves.append(f"提升到{int(level)}等時學會{name}")
                continue

            # 其他無法判定的也丟到 tutor（避免遺漏）
            if name:
                tutor_moves.append(name)

        parts = [form_label]
        if evo_moves:
            parts.append(f"進化時學會{_natural_join(evo_moves)}")
        if level_moves:
            parts.append(_natural_join(level_moves))
        if tutor_moves:
            parts.append(f"透過招式教學狂學會{_natural_join(tutor_moves)}")
        text = "，".join(parts).rstrip("，") + "。"

        record = {
            "doc_id": f"pokemon-{dex}-moves-learned-{i:03d}",
            "section": "moves_learned",
            "text": text,
            "metadata": {
                **meta,
                "form_region": region,
                "form_label": form_label,
                # "moves_learned": data_list  # 原始列表備查
            }
        }

        out_path = os.path.join(out_dir, f"{dex}-moves-learned-{i:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    return out_paths

# ---- moves: machine（TM） ----
def build_moves_machine_chunks(raw: Dict[str, Any], meta: Dict[str, Any], output_root: str) -> List[str]:
    """
    每個形態輸出一份 JSON：
      data/chunk/moves/machine/{dex}-moves-machine-001.json, ...
    文案範例：
      「急凍鳥 一般，可以透過招式學習器學會００１猛撞、００４可怕面孔…」
    """
    dex = meta["dex_index"]
    species_name = meta.get("name") or ""
    moves = raw.get("moves") or {}
    machine_blocks = moves.get("machine") or []

    out_dir = os.path.join(output_root, "moves")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: List[str] = []
    if not machine_blocks:
        placeholder = {
            "doc_id": f"pokemon-{dex}-moves-machine-001",
            "section": "moves_machine",
            "text": "招式學習器（TM）資料缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-moves-machine-001.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        return [out_path]

    for i, block in enumerate(machine_blocks, start=1):
        form_label_raw = (block.get("form") or "").strip()
        form_label = _ensure_species_in_label(form_label_raw, species_name)
        region = _extract_region_from_text(form_label)

        data_list = block.get("data") or []

        # 轉成「００１猛撞」這種樣式；若 machine_used 缺失，就用名稱
        tm_items = []
        for m in data_list:
            tm = (m.get("machine_used") or "").strip()
            name = (m.get("name") or "").strip()
            if tm and name:
                tm_items.append(f"{tm.replace('招式學習器', '').strip()}{name}" if "招式學習器" in tm else f"{tm}{name}")
            elif name:
                tm_items.append(name)

        text = f"{form_label}，可以透過招式學習器學會{_natural_join(tm_items)}。"

        record = {
            "doc_id": f"pokemon-{dex}-moves-machine-{i:03d}",
            "section": "moves_machine",
            "text": text,
            "metadata": {
                **meta,
                "form_region": region,
                "form_label": form_label,
                # "moves_machine": data_list
            }
        }

        out_path = os.path.join(out_dir, f"{dex}-moves-machine-{i:03d}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    return out_paths


# 8. 整理 動畫相關資訊 的content
def _nz(s: Optional[str]) -> str:
    return str(s or "").strip()

def _clean_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\u00A0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def build_anime_pokedex_chunk(raw: Dict[str, Any], meta: Dict[str, Any], output_root: str) -> str:
    """
    將 raw 中的動畫圖鑑資訊整理成單一句、用「；」分隔的文本，輸出成一份 JSON：
      data/chunk/anime/{dex}-anime-001.json

    目標文本格式（範例）：
      在動畫集數 EP249 中，小智 的圖鑑描述 噴火龍 為：強力的噴射火焰...（臺）；在動畫集數 BW116 中，小智 的圖鑑描述 噴火龍 為：...；
    """
    dex = meta["dex_index"]
    name = meta.get("name", "")  # 物種名

    # 來源 key（依你的資料而定，先支援常見命名）
    groups: List[Dict[str, Any]] = (
        raw.get("pokedex_info_anime")
        or raw.get("anime_pokedex")
        or []
    )

    out_dir = os.path.join(output_root, "anime")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{dex}-anime-001.json")

    if not groups:
        # 占位
        placeholder = {
            "doc_id": f"pokemon-{dex}-anime-001",
            "section": "pokedex_info_anime",
            "text": "動畫圖鑑描述資料缺失。",
            "metadata": {**meta}
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        return out_path

    bits: List[str] = []
    for g in groups:
        entries = g.get("entries") or []
        for e in entries:
            # 支援中英文欄位名
            ep    = _clean_text(_nz(e.get("集數") or e.get("episode")))
            owner = _clean_text(_nz(e.get("圖鑑持有人") or e.get("owner")))
            text  = _clean_text(_nz(e.get("內容") or e.get("text")))

            if not text:
                continue

            # 句尾補句點（避免原始文本沒句點時串接怪怪的）
            if not re.search(r"[。.!？?]$", text):
                text = text + "。"

            # 按你要的句型組句
            # 在動畫集數 EP249 中，小智 的圖鑑描述 噴火龍 為：{內容}
            head = "在動畫集數 "
            if ep:
                head += f"{ep} 中，"
            else:
                head += "（未標集數）中，"
            owner_part = f"{owner} 的圖鑑描述 " if owner else "圖鑑描述 "
            display = f"{head}{owner_part}{name} 為：{text}"
            # 去掉重複標點
            display = display.replace("。。", "。")
            # 結尾不加「。」，因為串接時會加「；」
            display = display.rstrip("。")

            bits.append(display)

    # 最終文本：用「；」連接，每段後面補上「；」，整體以「；」結尾（符合你的示例）
    if bits:
        text_all = "；".join(bits) + "；"
    else:
        text_all = "動畫圖鑑描述資料缺失。"

    record = {
        "doc_id": f"pokemon-{dex}-anime-001",
        "section": "pokedex_info_anime",
        "text": text_all,
        "metadata": {**meta}
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return out_path


# 9. 整理 命名來源 的content


# ----------------------------
# helpers
# ----------------------------

_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
_NONLATIN = re.compile(r"[^\x00-\x7F]")

def _clean_spaces(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.replace("\u00A0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _has_latin(s: str) -> bool:
    return bool(_LATIN.search(s or ""))

def _has_nonlatin(s: str) -> bool:
    return bool(_NONLATIN.search(s or ""))

def _split_name_and_romaji(name: str) -> Tuple[str, Optional[str]]:
    """
    嘗試把『名 + 羅馬拼音』拆成 (原名, 羅馬拼音)。
    規則：
      - 若同時含非拉丁與拉丁：選擇「第一個非拉丁片段」作為原名，「最後一段拉丁」作為羅馬拼音
      - 若只有拉丁：回傳 (name, None)
      - 若只有非拉丁：回傳 (name, None)
    """
    name = _clean_spaces(name)
    if not name:
        return "", None

    tokens = name.split()
    if _has_latin(name) and _has_nonlatin(name):
        nonlatin_tokens = [t for t in tokens if _has_nonlatin(t)]
        latin_tokens = [t for t in tokens if _has_latin(t) and not _has_nonlatin(t)]
        if nonlatin_tokens and latin_tokens:
            base = nonlatin_tokens[0]
            romaji = latin_tokens[-1]
            return base, romaji
        # 退化：抓最左非拉丁與最右拉丁
        base = None
        romaji = None
        for t in tokens:
            if _has_nonlatin(t):
                base = t
                break
        for t in reversed(tokens):
            if _has_latin(t) and not _has_nonlatin(t):
                romaji = t
                break
        return (base or name), romaji
    else:
        return name, None

def _dedup_zh_names(names: List[str]) -> str:
    """
    中文多來源常會重複（任天堂／臺灣／香港／大陸），取最常見的那個名稱。
    """
    names = [n for n in (_clean_spaces(x) for x in names) if n]
    if not names:
        return ""
    cnt = Counter(names)
    return cnt.most_common(1)[0][0]

def _normalize_origin_text(s: str) -> str:
    s = _clean_spaces(s)
    # 簡單把全形空格與多餘句點整理一下
    s = s.strip("。．.")
    # 括號內空白統一
    s = re.sub(r"（\s*", "（", s)
    s = re.sub(r"\s*）", "）", s)
    return s

def _format_clause(lang: str, name: str, origin: str) -> str:
    """
    生成「語言「名字（羅馬）」（＋語源）」的片段。
    name 內若含羅馬拼音，會拆成「名字（羅馬）」；若無，直接使用。
    origin 前自動加上「來自」等字樣時，保留原文，不再重複加。
    """
    base, romaji = _split_name_and_romaji(name)
    origin = _normalize_origin_text(origin)
    # 決定名字顯示
    if romaji:
        name_disp = f"{base}（{romaji}）"
    else:
        name_disp = base or name

    if not origin:
        return f"{lang}「{name_disp}」"

    # 若 origin 已經以「來自」「同英文名」「音譯」等開頭，就直接接
    if re.match(r"^(來自|同|為|音譯|沿用)", origin):
        return f"{lang}「{name_disp}」{origin}"
    else:
        return f"{lang}「{name_disp}」{origin}"

# ----------------------------
# main builder
# ----------------------------

def build_nameorigin_chunk(raw: Dict[str, Any], meta: Dict[str, Any], output_root: str) -> str:
    """
    讀取 raw['nameOrigin']（或 raw['name_origin']）的表格樣式字串，
    解析並整理成單行可讀語句，輸出到：
      data/chunk/nameorigin/{dex}-nameorigin.json

    規則：
      - 支援「| 語言 | 名字 | 來源 || ...」這種平鋪表格字串
      - 中文（任天堂／臺灣／香港／大陸）合併為一條，名稱取眾數，來源取第一個非空
      - 日文、韓文若同時出現非拉丁＋拉丁，顯示為「原名（羅馬）」格式
      - 其它語言直接一語一條，用全形分號「；」連接
    """
    dex = meta["dex_index"]
    out_dir = os.path.join(output_root, "nameorigin")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{dex}-nameorigin.json")

    raw_str = raw.get("nameOrigin") or raw.get("name_origin") or ""
    s = _clean_spaces(str(raw_str))
    if not s:
        # 無資料 → 占位
        record = {
            "doc_id": f"pokemon-{dex}-nameorigin",
            "section": "name_origin",
            "text": "名稱語源資料缺失。",
            "metadata": {**meta}
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return out_path

    # 將 | 分隔的表格清理，避免與正則衝突
    s = s.replace("|", "｜")
    s = re.sub(r"顯示更多.*$", "", s)

    # 抓取每列：｜ 語言 ｜（忽略一欄）｜ 名字 ｜ 來源 ｜ （雙豎線為分隔）
    row_pat = re.compile(r"｜\s*([^\｜]+?)\s*｜[^\｜]*?｜\s*([^\｜]+?)\s*｜\s*([^\｜]+?)\s*｜")
    rows = row_pat.findall(s)

    if not rows:
        # 無法解析也吐一份原文清理版
        record = {
            "doc_id": f"pokemon-{dex}-nameorigin",
            "section": "name_origin",
            "text": _clean_spaces(raw_str),
            "metadata": {**meta}
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return out_path

    # 收集
    zh_names: List[str] = []
    zh_origin: Optional[str] = None
    buckets: defaultdict[str, List[Tuple[str, str]]] = defaultdict(list)

    for lang, name, origin in rows:
        lang = _clean_spaces(lang)
        name = _clean_spaces(name)
        origin = _normalize_origin_text(origin)

        if not lang or not name:
            continue

        if lang.startswith("中文"):
            zh_names.append(name)
            if not zh_origin and origin:
                zh_origin = origin
        else:
            buckets[lang].append((name, origin))

    # 組中文（合併為一條）
    clauses: List[str] = []
    if zh_names:
        zh_label = "中文（任天堂／臺灣／香港／大陸）"
        zh_final_name = _dedup_zh_names(zh_names)
        zh_origin_text = zh_origin or ""
        clauses.append(_format_clause(zh_label, zh_final_name, zh_origin_text))

    # 其它語言逐條輸出
    # 為了穩定順序，這裡按照常見語言排序；其餘按字典序
    lang_order = ["日文", "英文", "法文", "德文", "義大利文", "西班牙文", "韓文", "俄文", "泰文", "印地文", "印尼文"]
    ordered_langs = [l for l in lang_order if l in buckets] + sorted([l for l in buckets if l not in lang_order])

    for lang in ordered_langs:
        for name, origin in buckets[lang]:
            clauses.append(_format_clause(lang, name, origin))

    # 組合文本
    text = "名稱語源：" + "；".join(clauses).rstrip("；") + "。"

    record = {
        "doc_id": f"pokemon-{dex}-nameorigin",
        "section": "name_origin",
        "text": text,
        "metadata": {**meta}
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return out_path



# 10. 整理 其他資訊 的content
def build_other_info_chunks(raw: Dict[str, Any], meta: Dict[str, Any], output_root: str) -> List[str]:
    """
    整理『其他資訊』，包含 preface、appearances、designOrigin、detail、other_info。
    每個主要欄位各輸出一份 JSON：
        data/chunk/other/{dex}-other-{key}.json
    所有段落使用全形分號（；）連接。
    若有多筆 other_info，會合併成一筆。
    """
    dex = meta["dex_index"]
    out_dir = os.path.join(output_root, "other")
    os.makedirs(out_dir, exist_ok=True)

    out_paths: List[str] = []

    def _join_with_semicolon(s: str) -> str:
        """把換行或多空白改成分號連接"""
        parts = [p.strip() for p in s.replace("—", "").replace("\n", "；").split("；") if p.strip()]
        return "；".join(parts)

    def _write_chunk(suffix: str, text: str, extra_meta: dict = None):
        if not text.strip():
            return
        record = {
            "doc_id": f"pokemon-{dex}-other-{suffix}",
            "section": "other",
            "text": text.strip(),
            "metadata": {**meta, **(extra_meta or {})}
        }
        out_path = os.path.join(out_dir, f"{dex}-other-{suffix}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    # ---- 主要四欄 ----
    for key in ["preface", "appearances", "designOrigin", "detail"]:
        text = raw.get(key, "")
        if isinstance(text, str) and text.strip():
            clean = _join_with_semicolon(text)
            _write_chunk(key, clean)

    # ---- 合併 other_info ----
    other_info = raw.get("other_info") or []
    if other_info:
        merged_parts = []
        for item in other_info:
            heading = (item.get("original_heading") or "").strip()
            content = (item.get("content") or "").strip()
            if heading and content:
                merged_parts.append(f"{heading}；{content}")
            elif content:
                merged_parts.append(content)
            elif heading:
                merged_parts.append(heading)
        text = "；".join(merged_parts)
        text = _join_with_semicolon(text)
        _write_chunk("otherinfo", text)

    # ---- 若全部都沒資料，輸出一份占位 ----
    if not out_paths:
        placeholder = {
            "doc_id": f"pokemon-{dex}-other-placeholder",
            "section": "other",
            "text": "其他資訊缺失。",
            "metadata": {**meta}
        }
        out_path = os.path.join(out_dir, f"{dex}-other-placeholder.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(placeholder, f, ensure_ascii=False, indent=2)
        out_paths.append(out_path)

    return out_paths



# === 主程式 ===
if __name__ == "__main__":
    PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    INPUT_DIR = os.path.join(PROJECT_ROOT, "data", "full")
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "chunk")
    IMAGE_ROOT = os.path.join(PROJECT_ROOT, "data", "images", "official")

    _REGION_KEYWORDS = ["阿羅拉", "伽勒爾", "洗翠", "帕底亞"]

    for filename in os.listdir(INPUT_DIR):
        if not filename.endswith(".json"):
            continue

        file_path = os.path.join(INPUT_DIR, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ JSON 格式錯誤：{filename}")
            continue

        # 1. 整理共用 metadata（內含寫檔）
        meta = normalize_metadata(raw, output_root=OUTPUT_DIR, image_root=IMAGE_ROOT)

        # 2. 整理 profile 的content
        build_profile_chunks(raw, meta, output_root=OUTPUT_DIR)

        # 3. 整理 進化鏈 的content
        build_evolution_chunk(raw, meta, output_root=OUTPUT_DIR)

        # 4. 整理 遊戲相關資訊 的content
        build_gameinfo_chunks(raw, meta, output_root=OUTPUT_DIR)

        # 5. 整理 總種族 的content
        build_stats_chunks(raw, meta, output_root=OUTPUT_DIR)

        # 6. 整理 圖鑑的介紹 的content
        build_pokedex_chunks(raw, meta, output_root=OUTPUT_DIR, mode="by_gen")

        # 7. 整理 可以學會的招式 的content
        build_moves_learned_chunks(raw, meta, output_root=OUTPUT_DIR)
        build_moves_machine_chunks(raw, meta, output_root=OUTPUT_DIR)

        # 8. 整理 動畫相關資訊 的content
        build_anime_pokedex_chunk(raw, meta, output_root=OUTPUT_DIR)

        # 9. 整理 命名來源 的content
        build_nameorigin_chunk(raw, meta, output_root=OUTPUT_DIR)

        # 10. 整理 其他資訊 的content
        build_other_info_chunks(raw, meta, output_root=OUTPUT_DIR)
        print(f"✅ 已處理 {filename}")
