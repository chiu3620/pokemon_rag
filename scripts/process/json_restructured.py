import pandas as pd
import os
import json
import shutil
import sys
import re

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 整理爬蟲資料的第1步
# 重購原始的json

# --- 解析器函數區 ---

def parse_pipe_delimited_table(text_block, headers_map):
    """
    一個通用的解析器，用於處理由 '|' 分隔的表格文字。
    :param text_block: 包含表格的完整文字。
    :param headers_map: 一個字典，將中文表頭映射到英文 key。
    """
    lines = text_block.strip().split('\n')
    if not lines:
        return []

    # 找到表頭行並建立欄位列表
    header_line = lines[0]
    header_keys = [headers_map.get(h.strip()) for h in header_line.split('|') if h.strip() and headers_map.get(h.strip())]
    if not header_keys:
        return [] # 如果找不到有效的表頭，則無法解析

    results = []
    # 從第二行開始處理資料
    for line in lines[1:]:
        if not line.strip() or line.strip() == '|':
            continue
        
        # 分割資料行，並移除前後的空元素
        values = [v.strip() for v in line.split('|')]
        if values[0] == '': values.pop(0)
        if values[-1] == '': values.pop(-1)

        # 檢查欄位數是否大致匹配
        if len(values) >= len(header_keys):
            item = {}
            for i, key in enumerate(header_keys):
                item[key] = values[i]
            # 將剩餘的值合併到最後一個欄位的筆記中
            if len(values) > len(header_keys) and 'notes' in item:
                 item['notes'] += ' ' + ' '.join(values[len(header_keys):])

            results.append(item)
    return results

def parse_evolution_text(text_block):
    """專門解析進化鏈文字的函數。"""
    chains = []
    # 使用 정규 표현식 尋找進化模式
    patterns = re.findall(r'\|\s*(.*?)\s*\|.*?→\s*\|\s*(.*?)\s*\|', text_block)
    for match in patterns:
        from_pokemon = match[0].replace('未進化', '').strip()
        to_pokemon = match[1].replace('1階進化', '').strip()
        method_match = re.search(r'\|\s*使用 (.*?)\s*→', text_block)
        method = method_match.group(1).strip() if method_match else "等級提升"
        
        chains.append({
            "from": from_pokemon,
            "to": to_pokemon,
            "method": method
        })
    return chains

# def parse_special_fields(data):
#     """
#     主解析函數，檢查並處理需要特殊解析的欄位。
#     """
#     # 名字來源 (name_etymology)
#     if 'name_etymology' in data and isinstance(data['name_etymology'], str):
#         headers = {"語言": "language", "名字": "name", "來源": "origin"}
#         parsed_data = parse_pipe_delimited_table(data['name_etymology'], headers)
#         if parsed_data: data['name_etymology'] = parsed_data

#     # 活動贈送 (eventGifts, 在 in_game_data 中)
#     if 'in_game_data' in data and isinstance(data['in_game_data'], str) and '活動贈送寶可夢' in data['in_game_data']:
#         headers = {"活動贈送寶可夢": "event_name", "等級": "level", "初訓家": "trainer_name", 
#                    "可接收的遊戲": "game", "版本": "version", "時間": "period", "特殊說明": "notes"}
#         # 為了簡化，我們假設 eventGifts 存在於 in_game_data 內
#         parsed_data = parse_pipe_delimited_table(data['in_game_data'], headers)
#         if parsed_data: data['event_gifts'] = parsed_data # 建立一個新欄位

#     # 進化鏈 (evolution_data)
#     if 'evolution_data' in data and isinstance(data['evolution_data'], str):
#         parsed_data = parse_evolution_text(data['evolution_data'])
#         if parsed_data: data['evolution_data'] = parsed_data

#     # 獲得方式 (acquisition) - 這是最複雜的，這裡只做一個簡化版示例
#     if 'in_game_data' in data and isinstance(data['in_game_data'], str) and '遊戲版本' in data['in_game_data']:
#         lines = data['in_game_data'].strip().split('\n')
#         acquisitions = []
#         current_gen = ""
#         # 由於其格式極不規則，這裡的解析非常簡化，僅作示範
#         for line in lines:
#             if "世代" in line:
#                 current_gen = line.strip()
#             elif "傳入" in line or "進化獲得" in line or "可見" in line:
#                  acquisitions.append({"generation_context": current_gen, "description": line.strip()})
#         if acquisitions:
#             data['acquisition_methods'] = acquisitions # 建立一個新欄位

#     return data


# --- 核心程式碼 (與前一版類似，但增加了 parse_special_fields 步驟) ---

def clean_empty_values(data):
    """遞迴地移除字典和列表中的空值。"""
    if isinstance(data, dict):
        return {k: v for k, v in ((k, clean_empty_values(v)) for k, v in data.items()) if v is not None and v != '' and v != [] and v != {}}
    if isinstance(data, list):
        return [v for v in (clean_empty_values(v) for v in data) if v is not None and v != '' and v != [] and v != {}]
    return data

def create_map_from_excel(rule_file_path):
    """從使用者指定的 Excel/CSV 檔案動態建立 heading 規則地圖。"""
    try:
        if rule_file_path.lower().endswith('.csv'): df = pd.read_csv(rule_file_path)
        elif rule_file_path.lower().endswith('.xlsx'): df = pd.read_excel(rule_file_path)
        else:
            print("錯誤: 不支援的規則檔案格式。")
            return None
    except FileNotFoundError:
        print(f"致命錯誤: 找不到規則檔案 '{rule_file_path}'。")
        return None
    except Exception as e:
        print(f"讀取規則檔案時發生錯誤: {e}")
        return None
    if len(df.columns) < 2:
        print("錯誤: Excel/CSV 規則檔案至少需要兩欄。")
        return None
    heading_map = {}
    source_col, target_col = df.columns[0], df.columns[1]
    df.dropna(subset=[source_col], inplace=True)
    for _, row in df.iterrows():
        source_key = str(row[source_col]).strip().replace('\n', ' ')
        target = "" if pd.isna(row[target_col]) else str(row[target_col]).strip()
        if target: heading_map[source_key] = target
    return heading_map

def process_file(source_path, output_path, rule_map):
    """完整的處理流程：重構 -> 解析特殊欄位 -> 清理 -> 儲存。"""
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            source_data = json.load(f)
    except (json.JSONDecodeError, IOError): return False

    # 步驟 1: 重構
    new_data = {k: v for k, v in source_data.items() if k != 'sections'}
    if 'sections' in source_data and isinstance(source_data['sections'], list):
        other_info = []
        for section in source_data['sections']:
            if isinstance(section, dict) and 'heading' in section:
                heading = section['heading'].strip().replace('\n', ' ')
                content = section.get('text', '').strip()
                target_key = rule_map.get(heading, "_OTHER_") # 預設為 _OTHER_
                if target_key == "_DELETE_": continue
                elif target_key != "_OTHER_":
                    if target_key in new_data: new_data[target_key] += f"\n\n--- (合併自: {heading}) ---\n\n{content}"
                    else: new_data[target_key] = content
                else: other_info.append({"original_heading": heading, "content": content})
        if other_info: new_data['other_info'] = other_info

    # 步驟 2: 解析特殊欄位
    # parsed_data = parse_special_fields(new_data)

    # 步驟 3: 深度清理
    cleaned_data = clean_empty_values(new_data)
            
    # 步驟 4: 儲存
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
        return True
    except IOError: return False

# --- 主程式執行區塊 ---
if __name__ == "__main__":
    print("--- JSON 重構 & 解析 & 清理工具 ---")

    try:
        rule_file_path = sys.argv[1]
    except IndexError:
        rule_file_path = os.path.join(PROJECT_ROOT, 'pokemon_headings_summary.xlsx')

    heading_rule_map = create_map_from_excel(rule_file_path)
    if heading_rule_map is None:
        input("因規則檔案問題，程式無法啟動。請按 Enter 鍵結束...")
        sys.exit()
    print(f"\n成功從 '{os.path.basename(rule_file_path)}' 載入 {len(heading_rule_map)} 條規則。")

    source_directory = os.path.join(PROJECT_ROOT, 'output', 'pokemon_json')
    output_directory = os.path.join(PROJECT_ROOT, 'output', 'pokemon_json_parsed_final_2')
    
    if not os.path.isdir(source_directory):
        print(f"錯誤: 來源資料夾 '{source_directory}' 不存在！")
        input("請按 Enter 鍵結束...")
        sys.exit()

    if os.path.isdir(output_directory):
        shutil.rmtree(output_directory)
    os.makedirs(output_directory)
    print(f"已建立全新的輸出資料夾: '{output_directory}'")
    print("-" * 30)

    files_to_process = [f for f in os.listdir(source_directory) if f.endswith('.json')]
    total_files = len(files_to_process)
    if total_files > 0:
        print(f"準備處理 {total_files} 個 JSON 檔案...")
        success_count = 0
        for i, filename in enumerate(files_to_process):
            source_path = os.path.join(source_directory, filename)
            output_path = os.path.join(output_directory, filename)
            if i > 0 and i % 100 == 0: print(f"  ...已處理 {i} 個檔案...")
            if process_file(source_path, output_path, heading_rule_map):
                success_count += 1
        print("-" * 30)
        print("所有檔案處理完成！")
        print(f"  - 成功處理: {success_count} / {total_files} 個檔案")
        print(f"  - 最終檔案已儲存至 '{output_directory}'")
    else:
        print("警告: 來源資料夾中沒有找到任何 .json 檔案。")