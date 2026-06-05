from backend.storage import load_thread, save_thread
from backend.models import ask_model


def add_message(thread, role, content, model=None):
    thread["messages"].append({
        "role": role,
        "content": content,
        "model": model
    })

def maybe_set_title(thread, user_message):
    if thread.get("title") == "New chat" and len(thread["messages"]) <= 1:
        thread["title"] = user_message[:40]  # limite propre

def chat(thread_id, user_message, model="coder"):
    thread = load_thread(thread_id)

    add_message(thread, "user", user_message, model)

    maybe_set_title(thread, user_message)

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in thread["messages"]
    ]

    response = ask_model(model, messages)

    add_message(thread, "assistant", response, model)

    save_thread(thread)

    return response, thread