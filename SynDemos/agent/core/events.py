"""
core/events.py
===============
Emission d'événements pendant un run : valide le type, construit l'objet,
le persiste en JSONL, et retourne la ligne SSE prête à yield.

Isolé du moteur FSM pour que celui-ci reste concentré sur la logique
d'exécution plutôt que sur le formatting/la persistance.
"""

from __future__ import annotations

from typing import Any, Optional

from config import EVENT_TYPES
from core.run_context import AgentContext
from schemas import AgentEvent
from storage.runs import append_event


def emit(ctx: AgentContext, type_: str, data: Optional[Any] = None) -> str:
    if type_ not in EVENT_TYPES:
        raise ValueError(f"Type d'événement inconnu: {type_}")

    event = AgentEvent(
        run_id=ctx.run_id,
        prompt=ctx.prompt,
        step=ctx.step,
        state=ctx.state,
        type=type_,
        data=data,
    )

    event_dict = event.model_dump()
    ctx.events.append(event_dict)
    append_event(ctx.run_id, event_dict)

    return event.to_jsonl()
