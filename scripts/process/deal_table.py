import pandas as pd
import os
import json
import shutil
import sys
import re

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# --- 1. 進階解析引擎 ---

GAME_VERSIONS_SET = {
    "紅", "綠", "藍", "皮卡丘", "金", "銀", "水晶版", "紅寶石", "藍寶石", "綠寶石", 
    "火紅", "葉綠", "鑽石", "珍珠", "白金", "心金", "魂銀", "黑", "白", "黑2", "白2",
    "Ｘ", "Ｙ", "歐米加紅寶石", "阿爾法藍寶石", "太陽", "月亮", "究極之日", "究極之月",
    "Let's Go！皮卡丘", "Let's Go！伊布", "劍", "盾", "晶燦鑽石", "明亮珍珠", 
    "傳說 阿爾宙斯", "朱", "紫", "劍／盾 擴展票", "朱／紫 零之祕寶"
}

def parse_in_game_data(text_block):
    """(進階版) 專為「獲得方式」與「活動贈送」設計的解析器。"""
    parsed_results = {}

    # --- Part A: 解析活動贈送 (Event Gifts) ---
    event_match = re.search(r'(\| 活動贈送寶可夢.*?\|)', text_block, re.DOTALL)
    if event_match:
        event_text = event_match.group(1)
        headers = {"活動贈送寶可夢": "event_name", "等級": "level", "初訓家": "trainer", "可接收的遊戲": "game", "版本": "version", "時間": "period", "特殊說明": "notes"}
        event_lines = [line.strip() for line in event_text.strip().split('\n') if line.strip()]
        if len(event_lines) > 1:
            header_keys = [headers.get(h.strip()) for h in event_lines[0].split('|') if h.strip() in headers]
            event_list = []
            for line in event_lines[1:]:
                if not line.startswith('|'): continue
                values = [v.strip() for v in line.strip('|').split('|')]
                if len(values) >= len(header_keys):
                    item = {key: values[i] for i, key in enumerate(header_keys)}
                    event_list.append(item)
            if event_list: parsed_results['event_gifts'] = event_list

    # --- Part B: 解析獲得方式 (Acquisition Methods) ---
    lines = [line.strip() for line in text_block.strip().split('\n') if line.strip()]
    lines = [line for line in lines if not any(k in line for k in ["世代", "寶可夢", "地點", "方式", "備註", "活動贈送寶可夢"])]

    acquisitions = []
    current_games = []
    i = 0
    while i < len(lines):
        line = lines[i]
        games_in_line = sorted([game for game in GAME_VERSIONS_SET if game in line], key=len, reverse=True)
        
        if games_in_line:
            current_games = games_in_line
            # 從行中移除遊戲名稱，得到剩餘的描述文字
            remaining_text = line
            for game in games_in_line: remaining_text = remaining_text.replace(game, '')
            
            description_lines = [remaining_text.strip()] if remaining_text.strip() else []
            i += 1
            while i < len(lines) and not any(g in lines[i] for g in GAME_VERSIONS_SET):
                description_lines.append(lines[i])
                i += 1
        else:
            i += 1
            continue

        full_description = ' '.join(filter(None, description_lines))
        if not full_description: continue

        # 解析描述
        method, location, notes = "野外捕捉", "N/A", []
        if "進化獲得" in full_description:
            method = "進化"
            match = re.search(r'由\s*(.*?)\s*進化', full_description)
            if match: notes.append(f"From {match.group(1)}")
        elif "傳入" in full_description: method = "需傳入"
        elif "不存在" in full_description: method = "遊戲中不存在"
        elif "巢穴" in full_description:
            location = "極巨巢穴"
            method = "極巨團體戰"
            notes.extend(re.findall(r'（.*?）', full_description))
        elif "太晶團體戰" in full_description:
            location = "太晶團體戰"
            method = "太晶團體戰"
            notes.extend(re.findall(r'★+', full_description))
        elif "搖動草叢" in full_description:
            method = "搖動草叢"
            location = description_lines[0]
        else:
            location = description_lines[0] if description_lines else "N/A"
            if len(description_lines) > 1: notes.extend(description_lines[1:])
        
        acquisitions.append({
            "games": current_games,
            "location": location.strip(),
            "method": method,
            "notes": ' '.join(notes).strip() or "N/A"
        })

    if acquisitions: parsed_results['acquisition_methods'] = acquisitions
    return parsed_results

def parse_evolution_data(text_block):
    """(進階版) 專為「進化」設計的解析器。"""
    chains = []
    patterns = re.findall(r'\|\s*([^|]*?進化\s*[^|]+?)\s*\|.*?→\s*\|\s*([^|]*?進化\s*[^|]+?)\s*\|', text_block)
    
    for from_raw, to_raw in patterns:
        from_poke = from_raw.replace('未進化', '').strip()
        to_poke = to_raw.replace('1階進化', '').replace('2階進化', '').strip()
        
        method = "等級提升"
        try:
            method_search_text = text_block.split(from_raw)[1].split(to_raw)[0]
            if "使用" in method_search_text:
                match = re.search(r'使用\s*(.*?)\s*→', method_search_text)
                if match: method = f"使用 {match.group(1).strip()}"
        except IndexError:
            pass # 某些格式可能導致分割失敗，忽略即可
        
        chains.append({"from": from_poke, "to": to_poke, "method": method})
    return chains if chains else text_block

def parse_name_etymology(text_block):
    """(進階版) 處理名字來源表格。"""
    lines = [line.strip() for line in text_block.strip().split('\n') if line.strip()]
    if not lines: return text_block
    
    headers = {"語言": "language", "名字": "name", "來源": "origin"}
    header_keys = [headers.get(h.strip()) for h in lines[0].split('|') if h.strip() in headers]
    if not header_keys: return text_block
    
    results = []
    for line in lines[1:]:
        if not line.startswith('|'): continue
        values = [v.strip() for v in line.strip('|').split('|')]
        
        if len(values) >= len(header_keys):
            item = {key: values[i] for i, key in enumerate(header_keys) if i < len(values)}
            results.append(item)
    return results if results else text_block

def clean_empty_values(data):
    if isinstance(data, dict):
        return {k: v for k, v in ((k, clean_empty_values(v)) for k, v in data.items()) if v is not None and v not in ['', [], {}]}
    if isinstance(data, list):
        return [v for v in (clean_empty_values(v) for v in data) if v is not None and v not in ['', [], {}]]
    return data

# --- 主程式執行區塊 ---
if __name__ == "__main__":
    print("--- 專用進階解析工具 ---")

    # --- 設定來源與輸出路徑 ---
    source_directory = os.path.join(PROJECT_ROOT, 'output', 'pokemon_json_parsed_final')
    output_directory = os.path.join(PROJECT_ROOT, 'output', 'pokemon_json_parsed_ultimate')
    
    if not os.path.isdir(source_directory):
        print(f"錯誤: 來源資料夾 '{source_directory}' 不存在！請先執行重構程式。")
        input("請按 Enter 鍵結束...")
        sys.exit()

    if os.path.isdir(output_directory):
        shutil.rmtree(output_directory)
    os.makedirs(output_directory)
    print(f"已建立全新的輸出資料夾: '{output_directory}'")
    print("-" * 30)

    # --- 開始處理檔案 ---
    files_to_process = [f for f in os.listdir(source_directory) if f.endswith('.json')]
    total_files = len(files_to_process)
    if total_files > 0:
        print(f"準備解析 {total_files} 個已重構的 JSON 檔案...")
        success_count = 0
        for i, filename in enumerate(files_to_process):
            source_path = os.path.join(source_directory, filename)
            output_path = os.path.join(output_directory, filename)
            
            try:
                with open(source_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # --- 在此處應用解析器 ---
                if 'name_etymology' in data and isinstance(data['name_etymology'], str):
                    data['name_etymology'] = parse_name_etymology(data['name_etymology'])

                if 'evolution_data' in data and isinstance(data['evolution_data'], str):
                    data['evolution_data'] = parse_evolution_data(data['evolution_data'])
                
                if 'in_game_data' in data and isinstance(data['in_game_data'], str):
                    parsed_game_data = parse_in_game_data(data['in_game_data'])
                    if 'acquisition_methods' in parsed_game_data:
                        data['acquisition_methods'] = parsed_game_data['acquisition_methods']
                    if 'event_gifts' in parsed_game_data:
                        data['event_gifts'] = parsed_game_data['event_gifts']
                    del data['in_game_data'] # 刪除已被解析的原始欄位

                # --- 清理所有空值 ---
                cleaned_data = clean_empty_values(data)

                # --- 儲存最終檔案 ---
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
                success_count += 1

            except Exception as e:
                print(f"處理檔案 {filename} 時發生錯誤: {e}")

        print("-" * 30)
        print("所有檔案解析完成！")
        print(f"  - 成功處理: {success_count} / {total_files} 個檔案")
        print(f"  - 最終檔案已儲存至 '{output_directory}'")
    else:
        print("警告: 來源資料夾中沒有找到任何 .json 檔案。")