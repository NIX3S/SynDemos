from pathlib import Path
import os
import glob

workspace = {}

def read_text_file(path):
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="ignore")

def list_directory(path="."):
    return os.listdir(path)

def search_files(path=".", pattern="*.py"):
    return glob.glob(f"{path}/**/{pattern}", recursive=True)

def write_text_file(path, content):
    Path(path).write_text(content, encoding="utf-8")
    workspace[path] = content
    return {"status": "created"}

def apply_patch(path, content):
    Path(path).write_text(content, encoding="utf-8")
    workspace[path] = content
    return {"status": "patched"}