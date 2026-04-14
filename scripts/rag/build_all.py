"""Run all chunking and indexing steps in order."""
import subprocess
import sys
import os

STEPS = [
    "chunk.py",
    "rag_build.py",
    "bm25_build_local.py",
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
    print("All indexing steps completed.")

if __name__ == "__main__":
    main()
