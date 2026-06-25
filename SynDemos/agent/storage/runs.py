"""
storage/runs.py
================
Gestion des runs en mémoire (actifs / archivés) + persistance JSONL
pour permettre le replay (/replay/{run_id}) même après que le run soit
terminé et retiré de la mémoire active.

Avant, RUNS/ARCHIVES vivaient comme des dicts globaux dans
configuration.py — fonctionnellement pareil ici, mais encapsulés
derrière une API pour pouvoir, plus tard, les swapper par un vrai
backend (Redis, SQLite) sans toucher au reste du code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from config import LOG_DIR

if TYPE_CHECKING:
    from core.run_context import AgentContext


class RunStore:
    def __init__(self):
        self._active: dict[str, "AgentContext"] = {}
        self._archived: dict[str, "AgentContext"] = {}

    # ---- runs actifs ----
    def register(self, ctx: "AgentContext") -> None:
        self._active[ctx.run_id] = ctx

    def get(self, run_id: str) -> "AgentContext | None":
        return self._active.get(run_id) or self._archived.get(run_id)

    def request_stop(self, run_id: str) -> bool:
        ctx = self._active.get(run_id)
        if ctx is None:
            return False
        ctx.stop_requested = True
        return True

    def archive(self, run_id: str) -> None:
        ctx = self._active.pop(run_id, None)
        if ctx is not None:
            self._archived[run_id] = ctx

    def is_active(self, run_id: str) -> bool:
        return run_id in self._active


runs = RunStore()


def log_path(run_id: str) -> Path:
    return LOG_DIR / f"{run_id}.jsonl"


def append_event(run_id: str, event: dict) -> None:
    with open(log_path(run_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(run_id: str) -> Iterator[dict]:
    path = log_path(run_id)
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
