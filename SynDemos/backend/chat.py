from backend.storage import load_thread, save_thread
from backend.models import ask_model
from backend import rag


def add_message(thread, role, content, model=None, **extra):
    """extra permet d'attacher des champs additionnels au message,
    typiquement `agent_log=[...]` et `run_id=...` pour les réponses de
    l'agent autonome (cf. backend/api.py /agent/stream)."""
    msg = {
        "role": role,
        "content": content,
        "model": model,
    }
    msg.update(extra)
    thread["messages"].append(msg)

    # Indexation RAG best-effort : ne doit jamais faire planter le chat
    # si Ollama n'a pas de modèle d'embedding installé.
    try:
        rag.index_message(thread["thread_id"], role, content, len(thread["messages"]) - 1)
    except Exception:
        pass


def maybe_set_title(thread, user_message):
    if thread.get("title") == "New chat" and len(thread["messages"]) <= 1:
        thread["title"] = user_message[:40]  # limite propre


def chat(thread_id, user_message, model="coder"):
    thread = load_thread(thread_id)

    add_message(thread, "user", user_message, model)

    maybe_set_title(thread, user_message)

    messages = rag.build_context(thread, user_message)

    response = ask_model(model, messages)

    add_message(thread, "assistant", response, model)

    save_thread(thread)

    return response, thread
