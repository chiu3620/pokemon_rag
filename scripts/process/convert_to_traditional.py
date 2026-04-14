import os
import json
from opencc import OpenCC

# 整理github的資料

# --- 設定 ---

# 1. 設定要轉換的目標資料夾
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROOT_DIRECTORY = os.path.join(PROJECT_ROOT, 'data')

# 2. 初始化 OpenCC，'s2t.json' 表示從簡體 (Simplified) 轉換到繁體 (Traditional)
cc = OpenCC('s2t')

# 3. ★★★ 新增：設定自訂的文字取代規則 ★★★
#    (這會在簡轉繁之後執行)
#    格式: {'要被取代的舊詞': '新的詞'}

#### 不要亂開，處理有點麻煩，之後還要手動確認文本中那些部分其實不用改
# CUSTOM_REPLACEMENTS = {
#     '霸道熊貓': '流氓熊貓',
#     '狡小狐': '偷兒狐'
# }

# --- 核心轉換函式 (已更新) ---

def convert_recursive(data):
    """
    遞迴地轉換一個 Python 物件，執行以下兩項操作：
    1. 內部所有字串從簡體到繁體。
    2. 執行自訂的詞語取代。
    """
    if isinstance(data, dict):
        # 如果是字典，轉換它的鍵和值
        return {convert_recursive(k): convert_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        # 如果是列表，轉換它的每一個元素
        return [convert_recursive(item) for item in data]
    elif isinstance(data, str):
        # 如果是字串，執行轉換流程
        # 步驟 A: 先執行 OpenCC 的簡轉繁
        converted_string = cc.convert(data)
        
        # 步驟 B: 接著執行自訂的取代規則
        for old_word, new_word in CUSTOM_REPLACEMENTS.items():
            converted_string = converted_string.replace(old_word, new_word)
            
        return converted_string
    else:
        # 其他資料型別 (數字、布林等) 保持不變
        return data

# --- 主程式 (已更新) ---

def main():
    """
    遍歷資料夾，從最深層開始處理檔案和資料夾。
    """
    if not os.path.isdir(ROOT_DIRECTORY):
        print(f"錯誤：找不到指定的資料夾 '{ROOT_DIRECTORY}'。請檢查路徑是否正確。")
        return

    print("警告：此程式將直接修改原始檔案和資料夾名稱。")
    print("強烈建議您在執行前備份整個資料夾。")
    # input("按 Enter 鍵繼續...")

    print(f"\n開始處理資料夾：{ROOT_DIRECTORY}")
    
    for dirpath, dirnames, filenames in os.walk(ROOT_DIRECTORY, topdown=False):
        
        # --- 1. 處理檔案 (內容轉換 + 重命名) ---
        for filename in filenames:
            original_filepath = os.path.join(dirpath, filename)
            
            # 僅處理 .json 檔案的內容
            if filename.lower().endswith('.json'):
                print(f"  處理 JSON 檔案內容: {original_filepath}")
                try:
                    with open(original_filepath, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                    
                    converted_content = convert_recursive(content)
                    
                    with open(original_filepath, 'w', encoding='utf-8') as f:
                        json.dump(converted_content, f, ensure_ascii=False, indent=4)
                        
                except json.JSONDecodeError:
                    print(f"    -> 警告：檔案 {filename} 不是有效的 JSON 格式，已跳過內容轉換。")
                except Exception as e:
                    print(f"    -> 錯誤：處理檔案 {filename} 時發生錯誤: {e}")

            # ★ 更新：對所有檔案進行重命名，使用包含自訂規則的完整轉換函式
            converted_filename = convert_recursive(filename)
            if converted_filename != filename:
                new_filepath = os.path.join(dirpath, converted_filename)
                print(f"  重命名檔案: {filename} -> {converted_filename}")
                try:
                    os.rename(original_filepath, new_filepath)
                except Exception as e:
                    print(f"    -> 錯誤：重命名檔案 {filename} 失敗: {e}")

        # --- 2. 處理資料夾 (重命名) ---
        for dirname in dirnames:
            original_dirpath = os.path.join(dirpath, dirname)
            # ★ 更新：對資料夾進行重命名，使用包含自訂規則的完整轉換函式
            converted_dirname = convert_recursive(dirname)
            if converted_dirname != dirname:
                new_dirpath = os.path.join(dirpath, converted_dirname)
                print(f"重命名資料夾: {dirname} -> {converted_dirname}")
                try:
                    os.rename(original_dirpath, new_dirpath)
                except Exception as e:
                    print(f"    -> 錯誤：重命名資料夾 {dirname} 失敗: {e}")

    print("\n所有檔案和資料夾處理完成！")


# 執行主程式
if __name__ == "__main__":
    main()