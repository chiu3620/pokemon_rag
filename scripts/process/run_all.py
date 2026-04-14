"""Run all data processing steps in order."""
import subprocess
import sys
import os

STEPS = [
    "clean_data.py",
    "convert_to_traditional.py",
    "json_restructured.py",
    "deal_table.py",
    "merge_all_json.py",
    "update_generation.py",
]

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in STEPS:
        path = os.path.join(script_dir, name)
        print(f"\n{'='*60}")
        print(f"▶ Running {name} ...")
        print(f"{'='*60}")
        result = subprocess.run([sys.executable, path])
        if result.returncode != 0:
            print(f"\n✖ {name} failed (exit code {result.returncode}). Aborting.")
            sys.exit(result.returncode)
        print(f"✔ {name} done.")
    print(f"\n{'='*60}")
    print("All processing steps completed.")

if __name__ == "__main__":
    main()
