from backend.storage import load_thread, save_thread
from backend.models import ask_model
from backend import rag


def add_message(thread, role, content, model=None, attachments=None, **extra):
    """`content` reste le texte brut tapé par l'utilisateur (affichage
    propre dans l'UI). `attachments` ([{filename, content}, ...]) est
    stocké séparément et fusionné avec `content` uniquement au moment de
    construire le contexte envoyé au LLM (cf. rag.message_text) et pour
    l'indexation RAG ci-dessous (pour pouvoir retrouver plus tard un
    détail mentionné dans un fichier joint).

    `extra` permet d'attacher d'autres champs au message, typiquement
    `agent_log=[...]` et `run_id=...` pour les réponses de l'agent
    autonome (cf. backend/api.py /agent/stream)."""
    msg = {
        "role": role,
        "content": content,
        "model": model,
    }
    if attachments:
        msg["attachments"] = attachments
    msg.update(extra)
    thread["messages"].append(msg)

    index_text = rag.message_text(msg)

    # Indexation RAG best-effort : ne doit jamais faire planter le chat
    # si Ollama n'a pas de modèle d'embedding installé.
    try:
        rag.index_message(thread["thread_id"], role, index_text, len(thread["messages"]) - 1)
    except Exception:
        pass


def maybe_set_title(thread, user_message):
    if thread.get("title") == "New chat" and len(thread["messages"]) <= 1:
        thread["title"] = user_message[:40]  # limite propre


def chat(thread_id, user_message, model="coder", attachments=None):
    thread = load_thread(thread_id)

    add_message(thread, "user", user_message, model, attachments=attachments)

    maybe_set_title(thread, user_message)

    messages = rag.build_context(thread, user_message)

    response = ask_model(model, messages)

    add_message(thread, "assistant", response, model)

    save_thread(thread)

    return response, thread
