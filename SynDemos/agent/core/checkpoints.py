"""
core/checkpoints.py
====================
Système de checkpoints fichiers pour permettre l'undo/rollback des
modifications faites par l'agent (write_file, edit_file).

Principe : avant CHAQUE écriture, on sauvegarde l'état précédent du
fichier (son contenu, ou None s'il n'existait pas) dans une pile par
run_id. `undo_last()` dépile et restaure — répéter l'appel revient en
arrière étape par étape, comme un undo classique d'éditeur.

Stocké en mémoire (par process) + persisté sur disque en JSONL dans
LOG_DIR pour survivre à un redémarrage tant que le run est encore
traçable (même répertoire que les logs d'événements).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import LOG_DIR, WORKSPACE


@dataclass
class Checkpoint:
    rel_path: str
    previous_content: Optional[str]  # None = le fichier n'existait pas avant
    new_content: str
    tool: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "rel_path": self.rel_path,
            "previous_content": self.previous_content,
            "new_content": self.new_content,
            "tool": self.tool,
            "timestamp": self.timestamp,
        }


class CheckpointStore:
    """Pile de checkpoints par run_id, avec persistance JSONL en doublon."""

    def __init__(self):
        self._stacks: dict[str, list[Checkpoint]] = {}

    def _checkpoint_log_path(self, run_id: str) -> Path:
        return LOG_DIR / f"{run_id}.checkpoints.jsonl"

    def record(
        self,
        run_id: str,
        rel_path: str,
        previous_content: Optional[str],
        new_content: str,
        tool: str,
    ) -> Checkpoint:
        cp = Checkpoint(
            rel_path=rel_path,
            previous_content=previous_content,
            new_content=new_content,
            tool=tool,
        )
        self._stacks.setdefault(run_id, []).append(cp)

        with open(self._checkpoint_log_path(run_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(cp.to_dict(), ensure_ascii=False) + "\n")

        return cp

    def list_checkpoints(self, run_id: str) -> list[Checkpoint]:
        return list(self._stacks.get(run_id, []))

    def undo_last(self, run_id: str) -> Optional[Checkpoint]:
        """
        Annule la dernière modification de fichier pour ce run : restaure
        previous_content sur disque (ou supprime le fichier s'il
        n'existait pas avant) et retourne le checkpoint annulé, ou None
        s'il n'y a plus rien à annuler.
        """
        stack = self._stacks.get(run_id)
        if not stack:
            return None

        cp = stack.pop()
        target = (WORKSPACE / cp.rel_path).resolve()

        # garde-fou : on ne restaure jamais hors du workspace, même si
        # rel_path a été corrompu d'une manière ou d'une autre.
        if WORKSPACE != target and WORKSPACE not in target.parents:
            return None

        if cp.previous_content is None:
            # le fichier n'existait pas avant cette modif -> on le supprime
            if target.exists():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(cp.previous_content, encoding="utf-8")

        return cp

    def undo_to(self, run_id: str, n: int) -> list[Checkpoint]:
        """Annule les n dernières modifications (dans l'ordre inverse), retourne celles annulées."""
        undone = []
        for _ in range(n):
            cp = self.undo_last(run_id)
            if cp is None:
                break
            undone.append(cp)
        return undone


checkpoints = CheckpointStore()
