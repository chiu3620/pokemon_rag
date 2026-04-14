#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan JSON files, list every field path (dot-notation), count total occurrences,
count how many files contain the field, and summarize observed data types.
Exports to Excel with helpful sheets.
"""
import os, json, argparse, collections
import pandas as pd
from typing import Any, Dict, Set, List, Tuple

def iter_json_files(in_dir: str, recursive: bool = True) -> List[str]:
    out = []
    for root, _, files in os.walk(in_dir):
        for fn in files:
            if fn.lower().endswith(".json"):
                out.append(os.path.join(root, fn))
        if not recursive:
            break
    return sorted(out)

def type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__

def walk(obj: Any, base: str, seen_paths: Dict[str, int], seen_types: Dict[str, Set[str]]):
    """Depth-first traversal to record field paths and types; arrays recurse into elements (same path)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = k if not base else f"{base}.{k}"
            seen_paths[path] = seen_paths.get(path, 0) + 1
            tn = type_name(v)
            seen_types.setdefault(path, set()).add(tn)
            walk(v, path, seen_paths, seen_types)
    elif isinstance(obj, list):
        # record the array node itself
        path = base
        # elements share the same base path (no index), so we just dive in
        for el in obj:
            walk(el, base, seen_paths, seen_types)
    else:
        # scalars are already accounted for at parent (we added path + type)
        pass

def analyze(files: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    field_total_counts: Dict[str, int] = {}
    field_file_counts: Dict[str, int] = {}
    field_types: Dict[str, Set[str]] = {}
    top_keys_counts: Dict[str, int] = {}

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            # skip bad JSON
            print(f"[WARN] Skip invalid JSON: {fp}: {e}")
            continue

        # top-level keys
        if isinstance(data, dict):
            for k in data.keys():
                top_keys_counts[k] = top_keys_counts.get(k, 0) + 1

        # traverse to count totals and types
        seen_paths_this_file: Set[str] = set()
        tmp_counts: Dict[str, int] = {}
        tmp_types: Dict[str, Set[str]] = {}
        walk(data, "", tmp_counts, tmp_types)

        # merge per-file counts into global totals
        for p, c in tmp_counts.items():
            field_total_counts[p] = field_total_counts.get(p, 0) + c
        for p, ts in tmp_types.items():
            if p not in field_types:
                field_types[p] = set()
            field_types[p].update(ts)
            seen_paths_this_file.add(p)

        # mark presence per file
        for p in seen_paths_this_file:
            field_file_counts[p] = field_file_counts.get(p, 0) + 1

    # Build DataFrames
    rows = []
    for p in sorted(field_total_counts.keys()):
        rows.append({
            "field_path": p,
            "files_with_field": field_file_counts.get(p, 0),
            "total_occurrences": field_total_counts.get(p, 0),
            "types_observed": ", ".join(sorted(field_types.get(p, set()))),
        })
    df_fields = pd.DataFrame(rows).sort_values(
        by=["files_with_field", "total_occurrences", "field_path"],
        ascending=[False, False, True]
    ).reset_index(drop=True)

    rows_top = []
    for k, cnt in sorted(top_keys_counts.items(), key=lambda x: (-x[1], x[0])):
        rows_top.append({"top_level_key": k, "files_with_key": cnt})
    df_top = pd.DataFrame(rows_top)

    return df_fields, df_top

def main():
    ap = argparse.ArgumentParser(description="Inventory JSON fields and output to Excel.")
    ap.add_argument("--in-dir", required=True, help="Directory containing JSON files (recursively scanned).")
    ap.add_argument("--out-xlsx", required=True, help="Path to output Excel file.")
    args = ap.parse_args()

    files = iter_json_files(args.in_dir, recursive=True)
    if not files:
        print("[ERROR] No JSON files found.")
        return

    print(f"[INFO] Found {len(files)} JSON files under {args.in_dir}")
    df_fields, df_top = analyze(files)

    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as writer:
        df_fields.to_excel(writer, sheet_name="by_field_path", index=False)
        df_top.to_excel(writer, sheet_name="top_level_keys", index=False)

    print(f"[DONE] Wrote Excel: {args.out_xlsx}")

if __name__ == "__main__":
    main()
