import os
import json
import shutil

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 整理爬蟲資料的第2步
# 清理資料


def remove_newlines_recursive(obj):
    """
    遞迴地遍歷一個物件 (字典或列表)，並移除所有字串值中的換行符 '\n'。
    """
    if isinstance(obj, dict):
        # 如果是字典，遍歷其鍵值對
        return {key: remove_newlines_recursive(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # 如果是列表，遍歷其元素
        return [remove_newlines_recursive(element) for element in obj]
    elif isinstance(obj, str):
        # 如果是字串，替換 '\n'
        return obj.replace('\n', '')
    else:
        # 其他類型 (數字、布林值等) 直接返回
        return obj

def process_json_file(file_path, copy_path):
    """
    讀取、清理並覆寫單一的 JSON 檔案。
    """
    try:
        # 步驟 1: 讀取檔案內容
        # 使用 'utf-8' 編碼來處理包含多國語言的檔案
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 步驟 2: 遞迴移除所有 '\n'
        cleaned_data = remove_newlines_recursive(data)

        # 步驟 3: 定義要刪除的鍵
        keys_to_delete = ["acquisition", "title", "infobox"]

        # 步驟 4: 刪除指定的鍵
        for key in keys_to_delete:
            if key in cleaned_data:
                del cleaned_data[key]
        
        # 步驟 5: 清理detail的內容
        noise_key = ['detail', 'designOrigin']
        for key in noise_key:
            if key in cleaned_data:
                temp = cleaned_data[key]
                temp = temp.split('|')[0]
                if temp:
                    cleaned_data[key] = temp
                else:
                    del cleaned_data[key]

        # 步驟 6: 將清理後的內容寫回原檔案
        with open(file_path, 'w', encoding='utf-8') as f:
            # ensure_ascii=False 確保中文字元能正常寫入
            # indent=4 讓輸出的 JSON 保持縮排，易於閱讀
            json.dump(cleaned_data, f, ensure_ascii=False, indent=4)
        
        # 步驟 7: 複製一份到另一個資料夾
        try:
            # 使用 shutil.copy2 複製檔案。copy2 會盡量保留檔案的中繼資料(例如修改時間)
            shutil.copy2(file_path, copy_path)
        except Exception as copy_error:
            print(f"  -> 複製檔案時發生錯誤: {copy_error}")
        print(f"成功處理: {file_path}")

    except json.JSONDecodeError:
        print(f"錯誤: {file_path} 不是一個有效的 JSON 檔案，已跳過。")
    except Exception as e:
        print(f"處理 {file_path} 時發生未預期的錯誤: {e}")


# --- 主程式開始 ---

# 您的 JSON 檔案所在的資料夾路徑
# r"..." 語法可以防止 Windows 路徑中的反斜線 '\' 被誤認為是跳脫字元
directory_path = os.path.join(PROJECT_ROOT, 'output', 'pokemon_json_parsed_final_2')

copy_path = os.path.join(PROJECT_ROOT, 'data', 'detail')

# 檢查路徑是否存在
if not os.path.isdir(directory_path):
    print(f"錯誤: 找不到資料夾 '{directory_path}'")
    print("請確認路徑是否正確。")
else:
    print(f"開始處理資料夾: {directory_path}\n")
    
    # 遍歷資料夾中的所有檔案
    for filename in os.listdir(directory_path):
        # 只處理 .json 結尾的檔案
        if filename.lower().endswith('.json'):
            # 組合出完整的檔案路徑
            full_path = os.path.join(directory_path, filename)
            process_json_file(full_path, copy_path)

    print("\n所有 JSON 檔案處理完畢！")