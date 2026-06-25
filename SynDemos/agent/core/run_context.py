"""
core/run_context.py
====================
État complet d'un run de l'agent.

Bug corrigé par rapport à l'ancien context.py : il y avait deux
`field(default_factory=...)` au niveau module, hors de toute classe —
ça lève NameError/TypeError à l'import (field() n'a aucun sens hors
d'un @dataclass). Tout est maintenant proprement dans AgentContext.

Ajout (style Claude Code) : une vraie todo list (`ctx.todos`) dérivée
du plan, que le moteur met à jour à chaque étape complétée. C'est ce
qui est streamé au client comme "todo_update" pour donner une vraie
visibilité sur l'avancement, comme le panneau de tâches de Claude Code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from schemas import Plan, TodoItem


class State:
    EXEC = "EXEC"
    VERIFY = "VERIFY"
    FIX = "FIX"
    DONE = "DONE"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class FileDiff:
    path: str
    diff: str


@dataclass
class AgentContext:
    prompt: str
    plan: Plan
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    messages: list[dict[str, Any]] = field(default_factory=list)
    state: str = State.EXEC
    step: int = 0

    tools_called: list[str] = field(default_factory=list)
    file_diffs: list[FileDiff] = field(default_factory=list)
    created_files: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)

    todos: list[TodoItem] = field(default_factory=list)

    execution_attempts: int = 0
    fix_attempts: int = 0
    fix_result: bool = False
    stop_requested: bool = False
    error: Optional[str] = None
    model_used: Optional[str] = None

    def mark_todo(self, todo_id: str, status: str) -> None:
        for t in self.todos:
            if t.id == todo_id:
                t.status = status
                return

    def next_pending_todo(self) -> Optional[TodoItem]:
        for t in self.todos:
            if t.status == "pending":
                return t
        return None

    def todos_as_dicts(self) -> list[dict[str, Any]]:
        return [t.model_dump() for t in self.todos]
