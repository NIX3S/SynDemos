import json
from pathlib import Path
import uuid
from datetime import datetime

DATA_DIR = Path("data/threads")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def delete_thread(thread_id):
    path = DATA_DIR / f"{thread_id}.json"
    if path.exists():
        path.unlink()
    return {"ok": True}

def create_thread(title="New chat"):
    thread_id = str(uuid.uuid4())

    thread = {
        "thread_id": thread_id,
        "title": title,
        "group": "Default",
        "messages": [],
        "created_at": str(datetime.now())
    }

    save_thread(thread)
    return thread


def save_thread(thread):
    path = DATA_DIR / f"{thread['thread_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(thread, f, indent=2, ensure_ascii=False)


def load_thread(thread_id):
    path = DATA_DIR / f"{thread_id}.json"
    if not path.exists():
        return None

    return json.load(open(path, "r", encoding="utf-8"))

'''
def list_threads():
    return [
        json.load(open(p, "r", encoding="utf-8"))
        for p in DATA_DIR.glob("*.json")
    ]
    '''
def list_threads():
    files = list(DATA_DIR.glob("*.json"))

    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return [
        json.load(open(p, "r", encoding="utf-8"))
        for p in files
    ]