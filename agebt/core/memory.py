import json
from datetime import datetime
from config import MEMORY_FILE

def load_memory():
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {"threads": []}

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def create_thread(user_input):
    memory = load_memory()

    thread = {
        "thread_id": str(datetime.now().timestamp()),
        "title": user_input[:40],
        "messages": [],
        "created_at": str(datetime.now())
    }

    memory["threads"].append(thread)
    save_memory(memory)

    return thread