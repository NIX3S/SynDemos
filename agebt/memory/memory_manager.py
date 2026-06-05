import json
import uuid
from datetime import datetime
from pathlib import Path

FILE = Path("memory/threads.json")

def load():
    if not FILE.exists():
        return {}
    return json.loads(FILE.read_text())

def save(data):
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def create_thread(title):
    data = load()
    tid = str(uuid.uuid4())

    data[tid] = {
        "thread_id": tid,
        "title": title,
        "messages": [],
        "created_at": str(datetime.now())
    }

    save(data)
    return tid

def get_thread(tid):
    return load().get(tid)

def append_message(tid, role, content, model=None):
    data = load()
    data[tid]["messages"].append({
        "role": role,
        "content": content,
        "model": model
    })
    save(data)