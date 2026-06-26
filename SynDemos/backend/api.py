import json

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from backend.chat import add_message, maybe_set_title, save_thread, load_thread
from backend.storage import create_thread, list_threads, DATA_DIR
from backend.models import ask_model_stream, ask_model
from backend.agent_client import ask_agent_stream, summarize_event, AGENT_URL
from backend import rag
from backend import files as file_extract

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# MODELS
# =========================

class Attachment(BaseModel):
    filename: str
    content: str


class ChatRequest(BaseModel):
    thread_id: str
    message: str
    model: str
    attachments: Optional[List[Attachment]] = None


class RenameRequest(BaseModel):
    thread_id: str
    title: str


class EditMessage(BaseModel):
    thread_id: str
    index: int
    content: str


class RegenerateRequest(BaseModel):
    thread_id: str


class NewThreadRequest(BaseModel):
    type: str = "chat"  # "chat" ou "agent"


class AgentChatRequest(BaseModel):
    thread_id: str
    message: str
    model: Optional[str] = None
    attachments: Optional[List[Attachment]] = None


class AgentStopRequest(BaseModel):
    force: bool = False


# =========================
# FICHIERS JOINTS
# =========================

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Reçoit un fichier (txt/py/md/pdf/docx/...), en extrait le texte et
    le renvoie au client. Le texte est attaché au message suivant côté
    UI (cf. /chat/stream et /agent/stream) — rien n'est persisté ici."""
    raw = await file.read()
    text, error = file_extract.extract_text(file.filename, raw)

    if error:
        return {"filename": file.filename, "error": error}

    return {"filename": file.filename, "content": text}


# =========================
# THREADS (CRUD)
# =========================

@app.post("/thread/new")
def new_thread(req: NewThreadRequest):
    return create_thread(thread_type=req.type)


@app.get("/threads")
def threads():
    return list_threads()


@app.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    return load_thread(thread_id)


@app.delete("/thread/{thread_id}")
def delete_thread_route(thread_id: str):
    from backend.storage import delete_thread

    rag.delete_index(thread_id)  # évite d'accumuler des fichiers d'embeddings orphelins
    return delete_thread(thread_id)


@app.post("/thread/rename")
def rename_thread(req: RenameRequest):
    thread = load_thread(req.thread_id)
    thread["title"] = req.title
    save_thread(thread)
    return thread


@app.post("/thread/group")
def set_group(req: RenameRequest):
    thread = load_thread(req.thread_id)
    thread["group"] = req.title
    save_thread(thread)
    return thread


class ReorderRequest(BaseModel):
    group: str
    thread_ids: list  # ordre désiré des thread_id, du 1er au dernier


@app.post("/thread/reorder")
def reorder_threads(req: ReorderRequest):
    """Fixe l'ordre d'affichage des threads d'un groupe (drag & drop dans
    l'UI). Tant qu'aucun ordre n'a jamais été fixé pour un groupe, le tri
    par défaut reste 'le plus récemment modifié en premier' (cf. list_threads)."""
    for i, thread_id in enumerate(req.thread_ids):
        thread = load_thread(thread_id)
        if thread is None:
            continue
        thread["group"] = req.group
        thread["order"] = i
        save_thread(thread)
    return {"ok": True}


# =========================
# CHAT CLASSIQUE (LLM via Ollama)
# =========================

@app.post("/chat/stream")
def chat_stream(req: ChatRequest, request: Request):

    thread = load_thread(req.thread_id)

    attachments = [a.dict() for a in req.attachments] if req.attachments else None
    add_message(thread, "user", req.message, req.model, attachments=attachments)
    maybe_set_title(thread, req.message)

    # Contexte = N derniers messages + rappel RAG des anciens messages
    # pertinents, plutôt que tout l'historique brut (cf. backend/rag.py).
    # message_text() fusionne automatiquement le contenu des pièces
    # jointes dans ce qui est envoyé au modèle.
    messages = rag.build_context(thread, req.message)

    def stream():
        full = ""

        for chunk in ask_model_stream(req.model, messages):
            full += chunk
            yield f"data: {json.dumps({'token': chunk, 'model': req.model})}\n\n"

        add_message(thread, "assistant", full, req.model)
        save_thread(thread)

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/chat")
def chat_api(req: ChatRequest):
    from backend.chat import chat

    attachments = [a.dict() for a in req.attachments] if req.attachments else None
    response, thread = chat(req.thread_id, req.message, req.model, attachments=attachments)
    return {
        "response": response,
        "thread": thread,
        "model": req.model,
    }


def _regenerate_thread(thread):
    """Régénère la réponse assistant à partir de l'état courant du thread
    (le dernier message utilisateur). L'appelant est responsable d'avoir
    déjà tronqué le thread si besoin (édition ou régénération ciblée)."""
    if not thread["messages"]:
        return ""

    last_model = thread["messages"][-1].get("model") or "coder"
    last_user_message = next(
        (m["content"] for m in reversed(thread["messages"]) if m["role"] == "user"),
        "",
    )

    if thread.get("type") == "agent" or last_model == "agent":
        return _run_agent_sync(thread, last_user_message)

    messages = rag.build_context(thread, last_user_message)
    response = ask_model(last_model, messages)
    add_message(thread, "assistant", response, last_model)
    return response


@app.post("/thread/regenerate")
def regenerate(req: RegenerateRequest):
    thread = load_thread(req.thread_id)
    response = _regenerate_thread(thread)
    save_thread(thread)
    return {"response": response}


class MessageRegenerateRequest(BaseModel):
    thread_id: str
    index: int  # index du message assistant à régénérer


@app.post("/message/regenerate")
def regenerate_message(req: MessageRegenerateRequest):
    """Régénère un message assistant précis SANS toucher au message
    utilisateur qui précède (contrairement à l'édition). On retire le
    message ciblé (et tout ce qui suit, par cohérence) puis on régénère."""
    thread = load_thread(req.thread_id)
    thread["messages"] = thread["messages"][: req.index]

    response = _regenerate_thread(thread)
    save_thread(thread)

    return {"response": response}


@app.post("/message/edit")
def edit_message(req: EditMessage):
    thread = load_thread(req.thread_id)

    thread["messages"][req.index]["content"] = req.content
    thread["messages"] = thread["messages"][: req.index + 1]
    save_thread(thread)
    return thread


# =========================
# AGENT AUTONOME
# =========================

def _run_agent_sync(thread, user_message):
    """Consomme entièrement le flux de l'agent (sans le streamer au
    client) et écrit le message assistant correspondant dans le thread.
    Utilisé par /thread/regenerate (pas de besoin de live streaming là)."""
    prompt = rag.build_agent_prompt(thread, user_message)

    answer = ""
    work_log = []
    run_id = None

    try:
        for evt in ask_agent_stream(prompt):
            etype = evt.get("type")
            data = evt.get("data", {}) or {}
            data_dict = data if isinstance(data, dict) else {}

            if etype == "start":
                run_id = data_dict.get("run_id")
            elif etype == "content_delta":
                answer += data_dict.get("text", "")
            elif etype == "final":
                if not answer:
                    answer = data_dict.get("content") or data_dict.get("response") or data_dict.get("result") or ""
            else:
                work_log.append({"type": etype, "data": data_dict, "line": summarize_event(evt)})
    except Exception as e:
        work_log.append({"type": "error", "line": f"⚠️ Agent inaccessible: {e}"})
        if not answer:
            answer = "Désolé, l'agent n'a pas pu répondre (vérifie qu'il tourne sur le port 8000)."

    add_message(
        thread,
        "assistant",
        answer or "(aucune réponse de l'agent)",
        "agent",
        agent_log=work_log,
        run_id=run_id,
    )

    return answer


@app.post("/agent/stream")
def agent_stream(req: AgentChatRequest):
    """Equivalent de /chat/stream mais pour l'agent autonome.

    Les événements bruts de l'agent sont reformatés en deux flux logiques
    côté client :
      - kind "work"   : étapes de travail de l'agent (plan, todos, tool
                         calls, vérifications...) -> affichées en direct
                         puis repliées sous un menu une fois terminé.
      - kind "answer" : le texte de la réponse finale -> reste affiché
                         normalement, comme un message de chat classique.
    """
    thread = load_thread(req.thread_id)

    attachments = [a.dict() for a in req.attachments] if req.attachments else None
    add_message(thread, "user", req.message, "agent", attachments=attachments)
    maybe_set_title(thread, req.message)

    prompt = rag.build_agent_prompt(thread, req.message)

    def stream():
        work_log = []
        answer = ""
        run_id = None

        try:
            for evt in ask_agent_stream(prompt, model=req.model):
                etype = evt.get("type")
                data = evt.get("data", {}) or {}

                if etype == "start":
                    run_id = data.get("run_id")
                    yield f"data: {json.dumps({'kind': 'run_id', 'run_id': run_id})}\n\n"

                elif etype == "content_delta":
                    text = data.get("text", "")
                    answer += text
                    yield f"data: {json.dumps({'kind': 'answer', 'text': text})}\n\n"

                elif etype == "final":
                    final_text = data.get("content") or data.get("response") or data.get("result")
                    if final_text and not answer:
                        answer = final_text
                        yield f"data: {json.dumps({'kind': 'answer', 'text': final_text})}\n\n"

                else:
                    line = summarize_event(evt)
                    work_log.append({"type": etype, "data": data, "line": line})
                    yield f"data: {json.dumps({'kind': 'work', 'line': line, 'event_type': etype})}\n\n"

        except Exception as e:
            err = f"⚠️ Agent inaccessible ou erreur de connexion ({AGENT_URL}): {e}"
            work_log.append({"type": "error", "line": err})
            yield f"data: {json.dumps({'kind': 'error', 'line': err})}\n\n"
            if not answer:
                answer = "Désolé, l'agent n'a pas pu répondre (vérifie qu'il tourne sur le port 8000)."

        add_message(
            thread,
            "assistant",
            answer or "(aucune réponse de l'agent)",
            "agent",
            agent_log=work_log,
            run_id=run_id,
        )
        save_thread(thread)

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/agent/stop/{run_id}")
def agent_stop(run_id: str, req: AgentStopRequest = AgentStopRequest()):
    """Proxy vers le /stop/{run_id} de l'agent (cf. son README : 1er appel
    = arrêt direct, sauf pip/pip3 en cours qui demande `force: true`)."""
    import requests

    try:
        r = requests.post(
            f"{AGENT_URL}/stop/{run_id}",
            json={"force": req.force},
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}
