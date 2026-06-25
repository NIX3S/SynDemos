"""
core/replay.py
================
Reproduit le flux d'événements d'un run terminé à partir du JSONL persisté.

Avant, replay_run existait dans executor.py mais n'était importé nulle
part dans api.py (le endpoint /replay appelait une fonction non importée
-> NameError au premier appel). Corrigé : importé et branché dans
api/routes.py.
"""

from __future__ import annotations

from typing import AsyncIterator

from storage.runs import read_events


async def replay_run(run_id: str) -> AsyncIterator[str]:
    import json

    for event in read_events(run_id):
        yield json.dumps(event, ensure_ascii=False) + "\n"
