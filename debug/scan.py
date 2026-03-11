import os
import re

search_dir = r"d:\Vtuber"
pattern = re.compile(r"companion", re.IGNORECASE)

count = 0
with open(r"d:\Vtuber\scan_results_utf8.txt", "w", encoding="utf-8") as out:
    for root, dirs, files in os.walk(search_dir):
        if "unity_web_build" in root or ".git" in root or "__pycache__" in root or ".venv" in root:
            continue
        for file in files:
            if file.endswith(".meta") or file.endswith(".pyc") or file.endswith(".dll") or file.endswith(".exe"):
                continue
            filepath = os.path.join(root, file)
            
            # Check filename
            if pattern.search(file):
                out.write(f"FILENAME: {filepath}\n")
                count += 1
                
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        if pattern.search(line):
                            out.write(f"{filepath}:{i+1}: {line.strip()[:100]}\n")
                            count += 1
            except Exception:
                pass
                
    out.write(f"Total matches: {count}\n")
