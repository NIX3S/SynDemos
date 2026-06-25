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


def create_thread(title="New chat", thread_type="chat"):
    """thread_type: 'chat' (LLM classique) ou 'agent' (agent autonome)."""
    thread_id = str(uuid.uuid4())

    thread = {
        "thread_id": thread_id,
        "title": title,
        "group": "Agents" if thread_type == "agent" else "Default",
        "type": thread_type,
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

    thread = json.load(open(path, "r", encoding="utf-8"))
    thread.setdefault("type", "chat")  # rétro-compat threads créés avant ce champ
    return thread


def list_threads():
    files = list(DATA_DIR.glob("*.json"))

    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    threads = []
    for p in files:
        t = json.load(open(p, "r", encoding="utf-8"))
        t.setdefault("type", "chat")
        threads.append(t)

    return threads
