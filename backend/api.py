from fastapi import FastAPI
from pydantic import BaseModel
from backend.chat import chat,add_message, maybe_set_title
from backend.storage import create_thread, load_thread, list_threads,save_thread,DATA_DIR
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    model: str

class RenameRequest(BaseModel):
    thread_id: str
    title: str


@app.post("/thread/rename")
def rename_thread(req: RenameRequest):
    thread = load_thread(req.thread_id)
    thread["title"] = req.title
    save_thread(thread)
    return thread

from fastapi.responses import StreamingResponse
import json

from fastapi.responses import StreamingResponse
import json
from backend.chat import add_message, maybe_set_title, save_thread, load_thread
from backend.models import ask_model_stream, ask_model


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, request: Request):

    thread = load_thread(req.thread_id)

    add_message(thread, "user", req.message, req.model)
    maybe_set_title(thread, req.message)

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in thread["messages"]
    ]

    def stream():
        full = ""

        for chunk in ask_model_stream(req.model, messages):
            full += chunk
            yield f"data: {json.dumps({'token': chunk, 'model': req.model})}\n\n"

        add_message(thread, "assistant", full, req.model)#
        save_thread(thread)

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
@app.post("/chat")
def chat_api(req: ChatRequest):
    response, thread = chat(req.thread_id, req.message, req.model)#
    return {
        "response": response,
        "thread": thread,
        "model": req.model
    }

class EditMessage(BaseModel):
    thread_id: str
    index: int
    content: str

class RegenerateRequest(BaseModel):
    thread_id: str

@app.post("/thread/regenerate")
def regenerate(req: RegenerateRequest):

    thread = load_thread(req.thread_id)

    messages = [
        {
            "role": m["role"],
            "content": m["content"]
        }
        for m in thread["messages"]
    ]

    response = ask_model(
        thread["messages"][-1]["model"],
        messages
    )

    add_message(
        thread,
        "assistant",
        response,
        thread["messages"][-1]["model"]
    )

    save_thread(thread)

    return {"response": response}
    
@app.post("/message/edit")
def edit_message(req: EditMessage):
    thread = load_thread(req.thread_id)

    thread["messages"][req.index]["content"] = req.content
    thread["messages"] = thread["messages"][:req.index + 1]
    save_thread(thread)
    return thread

@app.post("/thread/group")
def set_group(req: RenameRequest):
    thread = load_thread(req.thread_id)
    thread["group"] = req.title
    save_thread(thread)
    return thread

@app.delete("/thread/{thread_id}")
def delete_thread(thread_id: str):
    from backend.storage import delete_thread
    return delete_thread(thread_id)

@app.post("/thread/new")
def new_thread():
    return create_thread()


@app.get("/threads")
def threads():
    return list_threads()


@app.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    return load_thread(thread_id)