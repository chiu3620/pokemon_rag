import os
import json

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# --- 請在這裡設定您的路徑 ---
# 目標資料夾：存放所有需要處理的寶可夢詳細資料
TARGET_POKEMON_DIRECTORY = os.path.join(PROJECT_ROOT, 'data', 'full')

# ======================================================================
#
# ★★★ 如果還有其他要刪除的 key，請修改這裡！ ★★★
#
# 只要在下面的列表中新增或移除字串即可。
# 例如：若要同時刪除 'reference' 和 'meta'，就改成：
# KEYS_TO_DELETE = ['reference', 'meta']
#
KEYS_TO_DELETE = ['reference']
#
# ======================================================================


def batch_remove_keys_from_json(target_dir, keys_to_remove):
    """
    批次從一個資料夾內的所有 JSON 檔案中，刪除指定的 key。

    Args:
        target_dir (str): 目標資料夾的路徑。
        keys_to_remove (list): 一個包含要刪除的 key 名稱的列表 (list of strings)。
    """
    if not keys_to_remove:
        print("資訊：要刪除的 key 列表是空的，程式已結束。")
        return

    if not os.path.isdir(target_dir):
        print(f"錯誤：目標資料夾 '{target_dir}' 不存在。")
        return

    print(f"準備開始處理資料夾 '{target_dir}'...")
    print(f"將會尋找並刪除以下 key: {keys_to_remove}")
    print("-" * 40)

    # 初始化計數器
    processed_files = 0
    updated_files = 0
    
    # 遍歷目標資料夾中的所有檔案
    for filename in os.listdir(target_dir):
        if filename.endswith('.json'):
            processed_files += 1
            file_path = os.path.join(target_dir, filename)
            
            try:
                # 讀取 JSON 檔案
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 標記此檔案是否被修改過
                was_modified = False
                
                # 檢查列表中每一個要刪除的 key
                for key in keys_to_remove:
                    if key in data:
                        # 如果 key 存在，就刪除它
                        del data[key]
                        was_modified = True
                        print(f"-> 在檔案 '{filename}' 中刪除了 key: '{key}'")
                
                # 只有在檔案內容被修改過的情況下，才進行寫入
                if was_modified:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    updated_files += 1

            except json.JSONDecodeError:
                print(f"警告：檔案 '{filename}' 的 JSON 格式不正確，已跳過。")
            except Exception as e:
                print(f"錯誤：處理檔案 '{filename}' 時發生未預期錯誤: {e}，已跳過。")

    print("-" * 40)
    print("=== 處理完成 ===")
    print(f"總共掃描檔案數量: {processed_files}")
    print(f"成功更新檔案數量: {updated_files}")

# --- 執行主程式 ---
if __name__ == "__main__":
    batch_remove_keys_from_json(TARGET_POKEMON_DIRECTORY, KEYS_TO_DELETE)