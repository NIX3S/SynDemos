"""
schemas.py
==========
Contrats de données partagés entre les couches (API <-> moteur <-> client SSE).

Centraliser ces modèles évite la dérive silencieuse qu'on avait avant
(ex: l'event "exec" qui transportait des clés différentes selon l'endroit
du code qui l'émettait).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requêtes entrantes
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    prompt: str
    model: Optional[str] = None  # override ponctuel du modèle (doit être whitelisté)


# ---------------------------------------------------------------------------
# Plan / Todo
# ---------------------------------------------------------------------------
class TodoItem(BaseModel):
    id: str
    label: str
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"


class Plan(BaseModel):
    need_code: bool = False
    need_execution: bool = False
    task_category: str = "code"  # "code" | "redaction" | "synthese" | "reflexion"
    steps: list[str] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evénements de stream (SSE)
# ---------------------------------------------------------------------------
class AgentEvent(BaseModel):
    run_id: str
    prompt: str
    step: int
    state: str
    type: str
    data: Optional[Any] = None

    def to_jsonl(self) -> str:
        return self.model_dump_json() + "\n"


# ---------------------------------------------------------------------------
# Résultats d'outils (forme normalisée — tous les outils retournent ceci)
# ---------------------------------------------------------------------------
class ToolResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
