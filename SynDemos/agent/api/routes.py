"""
api/routes.py
==============
Endpoints HTTP. Mêmes routes que l'ancien api.py, mais :
- /replay/{run_id} importe réellement replay_run (avant: NameError au
  premier appel, la fonction n'était jamais importée)
- /debug/{run_id} fonctionne aussi sur des runs archivés (avant : ne
  cherchait que dans RUNS, donc un run terminé devenait introuvable
  immédiatement après son archivage)
- 404 explicite avec status code correct au lieu de {"error": "not found"}
  avec un 200 implicite
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.checkpoints import checkpoints
from core.engine import run_ask_stream
from core.memory import memory
from core.replay import replay_run
from schemas import AskRequest
from storage.runs import runs
from tools import process_registry

router = APIRouter()


class UndoRequest(BaseModel):
    steps: int = 1  # nombre de modifications de fichiers à annuler, en partant de la plus récente


class StopRequest(BaseModel):
    force: bool = False  # confirme l'arrêt d'une commande protégée (pip install...) déjà signalée


@router.get("/")
def root():
    return {"status": "ok", "memory_turns": len(memory)}


@router.get("/tools")
def list_tools():
    """
    Diagnostic : liste les outils réellement enregistrés et exposés au
    LLM à cet instant (function-calling schemas). Utile pour vérifier
    sans ambiguïté qu'un outil attendu (ex: web_search) est bien chargé,
    plutôt que de le découvrir au milieu d'un run.
    """
    from tools.registry import all_tool_schemas

    schemas = all_tool_schemas()
    return {
        "count": len(schemas),
        "tools": [
            {"name": s["function"]["name"], "description": s["function"]["description"]}
            for s in schemas
        ],
    }


@router.post("/ask")
async def ask(req: AskRequest):
    return StreamingResponse(
        run_ask_stream(req),
        media_type="text/event-stream",
    )


@router.get("/replay/{run_id}")
async def replay(run_id: str):
    ctx = runs.get(run_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="run introuvable")

    return StreamingResponse(
        replay_run(run_id),
        media_type="text/event-stream",
    )


@router.get("/debug/{run_id}")
def debug(run_id: str):
    ctx = runs.get(run_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="run introuvable")

    return {
        "run_id": ctx.run_id,
        "state": ctx.state,
        "step": ctx.step,
        "model_used": ctx.model_used,
        "task_category": ctx.plan.task_category if ctx.plan else None,
        "tools_called": ctx.tools_called,
        "created_files": sorted(ctx.created_files),
        "todos": ctx.todos_as_dicts(),
        "events": ctx.events,
        "error": ctx.error,
    }


@router.post("/stop/{run_id}")
def stop(run_id: str, req: StopRequest = StopRequest()):
    """
    Demande l'arrêt du run. Le flag stop_requested est toujours posé
    immédiatement (le streaming LLM s'arrêtera dès le prochain token).

    Si une commande shell "protégée" est en cours (ex: pip install...),
    elle n'est PAS tuée par ce premier appel — la réponse contient
    status="confirmation_required" avec la commande et sa durée actuelle.
    Il faut rappeler /stop avec {"force": true} pour vraiment l'interrompre.
    Une commande shell normale (script, etc.) est tuée immédiatement, sans
    confirmation nécessaire.
    """
    found = runs.request_stop(run_id)
    if not found:
        raise HTTPException(status_code=404, detail="run introuvable ou déjà terminé")

    kill_result = process_registry.kill(run_id, force=req.force)

    return {"ok": True, **kill_result}


@router.get("/checkpoints/{run_id}")
def list_checkpoints(run_id: str):
    """Liste les modifications de fichiers faites pendant ce run, dans l'ordre
    chronologique — utile pour choisir combien d'étapes annuler avec /undo."""
    cps = checkpoints.list_checkpoints(run_id)
    return {
        "run_id": run_id,
        "count": len(cps),
        "checkpoints": [cp.to_dict() for cp in cps],
    }


@router.post("/undo/{run_id}")
def undo(run_id: str, req: UndoRequest = UndoRequest()):
    """
    Annule les `steps` dernières modifications de fichiers faites par
    l'agent pendant ce run (write_file/edit_file), dans l'ordre inverse
    (la plus récente d'abord). Restaure le contenu précédent sur disque,
    ou supprime le fichier s'il n'existait pas avant la modification.
    """
    if req.steps < 1:
        raise HTTPException(status_code=400, detail="steps doit être >= 1")

    undone = checkpoints.undo_to(run_id, req.steps)

    if not undone:
        raise HTTPException(
            status_code=404,
            detail="rien à annuler pour ce run (aucun checkpoint trouvé ou pile déjà vide)",
        )

    return {
        "ok": True,
        "undone_count": len(undone),
        "undone": [
            {"rel_path": cp.rel_path, "tool": cp.tool, "timestamp": cp.timestamp}
            for cp in undone
        ],
    }
