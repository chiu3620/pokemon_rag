# -*- coding: utf-8 -*-
"""
Created on Mon Oct 13 02:12:07 2025

@author: chiu3
"""

import os
import json

# 整理資料的第4步
# 把世代的資料補上去

# --- 請在這裡設定您的路徑 ---
# 來源檔案：包含所有寶可夢世代資訊的列表
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

SOURCE_GENERATION_FILE = os.path.join(PROJECT_ROOT, 'data', 'pokemon_full_list.json')
# 目標資料夾：存放所有需要更新的寶可夢詳細資料
TARGET_POKEMON_DIRECTORY = os.path.join(PROJECT_ROOT, 'data', 'full')

def batch_update_pokemon_files(source_path, target_dir):
    """
    批次更新一個資料夾內所有寶可夢 JSON 檔案，為其新增世代資訊。

    Args:
        source_path (str): 來源 JSON 檔案的路徑 (包含世代列表)。
        target_dir (str): 目標資料夾的路徑 (包含多個寶可夢詳細資料檔)。
    """
    # 1. 讀取世代資訊來源檔案，並建立快速查找字典
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            generations_data = json.load(f)
        
        # 建立一個以 index 為鍵，generation 為值的字典
        # 例如: {'0001': '第一世代', '0002': '第一世代', ...}
        generation_lookup = {
            pokemon['index']: pokemon['generation'] for pokemon in generations_data
        }
        print(f"成功從 {source_path} 載入 {len(generation_lookup)} 筆寶可夢世代資訊。")
    except FileNotFoundError:
        print(f"錯誤：找不到來源檔案 '{source_path}'。請確認檔案是否存在於同一個資料夾中。")
        return
    except json.JSONDecodeError:
        print(f"錯誤：來源檔案 '{source_path}' 的 JSON 格式不正確。")
        return

    # 檢查目標資料夾是否存在
    if not os.path.isdir(target_dir):
        print(f"錯誤：目標資料夾 '{target_dir}' 不存在。請確認資料夾名稱是否正確。")
        return

    print("-" * 30)
    updated_count = 0
    skipped_count = 0

    # 2. 遍歷目標資料夾中的所有檔案
    for filename in os.listdir(target_dir):
        # 我們只處理 .json 結尾的檔案
        if filename.endswith('.json'):
            file_path = os.path.join(target_dir, filename)
            
            try:
                # 3. 讀取目標寶可夢檔案
                with open(file_path, 'r', encoding='utf-8') as f:
                    pokemon_data = json.load(f)
                
                # 如果檔案已存在 generation 欄位，則跳過，避免重複寫入
                if 'generation' in pokemon_data:
                    # print(f"資訊：'{filename}' 已有世代資訊，跳過。")
                    skipped_count += 1
                    continue

                pokemon_index = pokemon_data.get('index')
                if not pokemon_index:
                    print(f"警告：'{filename}' 中找不到 'index' 欄位，已跳過。")
                    skipped_count += 1
                    continue

                # 4. 從查找字典中找到對應的 generation
                generation_info = generation_lookup.get(pokemon_index)

                if generation_info:
                    # 5. 將 generation 資訊新增到資料中
                    pokemon_data['generation'] = generation_info
                    
                    # 6. 將更新後的資料寫回原檔案
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(pokemon_data, f, ensure_ascii=False, indent=4)
                    
                    print(f"成功：已將 '{generation_info}' 新增至 '{filename}'。")
                    updated_count += 1
                else:
                    print(f"警告：在來源資料中找不到索引為 {pokemon_index} 的世代資訊 ('{filename}')，已跳過。")
                    skipped_count += 1

            except json.JSONDecodeError:
                print(f"錯誤：'{filename}' 檔案格式不正確，已跳過。")
                skipped_count += 1
            except Exception as e:
                print(f"處理 '{filename}' 時發生未預期錯誤: {e}，已跳過。")
                skipped_count += 1
    
    print("-" * 30)
    print("=== 處理完成 ===")
    print(f"成功更新檔案數量: {updated_count}")
    print(f"跳過檔案數量 (已存在或資料不齊): {skipped_count}")

# --- 執行主程式 ---
if __name__ == "__main__":
    batch_update_pokemon_files(SOURCE_GENERATION_FILE, TARGET_POKEMON_DIRECTORY)