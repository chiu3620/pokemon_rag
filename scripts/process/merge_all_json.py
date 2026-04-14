import os
import json
# 整理資料的第3步
# 將爬下來的資料跟另一個github的資料merge再一起


# --- 請在這裡修改您的資料夾路徑 ---
# 1. 基礎資料夾：存放有數字編號的檔案 (例如: '0038-九尾.json')
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

BASE_DIRECTORY = os.path.join(PROJECT_ROOT, 'data', 'pokemon')

# 2. 來源資料夾：存放沒有數字編號的檔案 (例如: '九尾.json')
SOURCE_DIRECTORY = os.path.join(PROJECT_ROOT, 'data', 'detail')

# 3. 輸出資料夾：用來存放合併後的新檔案
OUTPUT_DIRECTORY = os.path.join(PROJECT_ROOT, 'data', 'full')
# --- 路徑設定結束 ---

def merge_json_from_folders():
    """
    遍歷基礎資料夾，尋找來源資料夾中的對應檔案進行合併，
    並將結果儲存到輸出資料夾。
    """
    # 檢查輸入路徑是否存在
    if not os.path.isdir(BASE_DIRECTORY):
        print(f"錯誤：找不到基礎資料夾 '{BASE_DIRECTORY}'")
        return
    if not os.path.isdir(SOURCE_DIRECTORY):
        print(f"錯誤：找不到來源資料夾 '{SOURCE_DIRECTORY}'")
        return

    # 如果輸出資料夾不存在，則自動建立它
    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)
    print(f"輸出將會儲存到: {OUTPUT_DIRECTORY}\n")

    # 遍歷基礎資料夾中的所有檔案
    for base_filename in os.listdir(BASE_DIRECTORY):
        # 只處理 .json 檔案
        if not base_filename.lower().endswith('.json'):
            continue

        try:
            # --- 核心邏輯：從 '0038-九尾.json' 推出 '九尾.json' ---
            # 透過 '-' 分割檔名，並取第二部分
            parts = base_filename.split('-', 1)
            if len(parts) < 2:
                print(f"警告：檔名 '{base_filename}' 格式不符 (缺少'-')，已跳過。")
                continue
            
            source_filename = parts[1]
            # --- 核心邏輯結束 ---

            base_filepath = os.path.join(BASE_DIRECTORY, base_filename)
            source_filepath = os.path.join(SOURCE_DIRECTORY, source_filename)

            # 檢查對應的來源檔案是否存在
            if not os.path.isfile(source_filepath):
                print(f"警告：在來源資料夾中找不到 '{base_filename}' 對應的檔案 '{source_filename}'，已跳過。")
                continue

            # 讀取兩個 JSON 檔案的內容
            with open(base_filepath, 'r', encoding='utf-8') as f:
                base_data = json.load(f)
            
            with open(source_filepath, 'r', encoding='utf-8') as f:
                source_data = json.load(f)

            # 將來源檔案的資料合併到基礎資料中
            base_data.update(source_data)

            # 設定輸出的完整路徑和檔名
            output_filepath = os.path.join(OUTPUT_DIRECTORY, base_filename)

            # 將合併後的資料寫入新檔案
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(base_data, f, ensure_ascii=False, indent=4)
            
            print(f"成功合併: '{base_filename}' + '{source_filename}' -> 已儲存")

        except json.JSONDecodeError:
            print(f"錯誤：檔案 '{base_filename}' 或其對應檔案的 JSON 格式有誤，已跳過。")
        except Exception as e:
            print(f"處理檔案 '{base_filename}' 時發生未預期錯誤: {e}")

    print("\n所有檔案處理完畢！")


# --- 執行主程式 ---
if __name__ == "__main__":
    merge_json_from_folders()