"""
core/memory.py
===============
Mémoire conversationnelle courte (les N derniers échanges), utilisée pour
donner du contexte au planner/exécuteur entre deux requêtes /ask.

Changement par rapport à l'ancien memory.py : ce n'est plus une liste
globale mutable importée partout (MEMORY dans configuration.py), mais une
classe instanciée une fois, ce qui la rend testable et évite les imports
circulaires entre configuration/memory/llm qu'on avait avant.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import MEMORY_MAX_TURNS


@dataclass
class MemoryTurn:
    user: str
    assistant: str


class ConversationMemory:
    def __init__(self, max_turns: int = MEMORY_MAX_TURNS):
        self.max_turns = max_turns
        self._turns: list[MemoryTurn] = []

    def update(self, user: str, assistant: str) -> None:
        self._turns.append(MemoryTurn(user=user, assistant=assistant))
        if len(self._turns) > self.max_turns:
            self._turns.pop(0)

    def build_context(self) -> str:
        if not self._turns:
            return ""
        return "\n".join(
            f"User: {t.user}\nAssistant: {t.assistant}" for t in self._turns
        )

    def __len__(self) -> int:
        return len(self._turns)


# Instance partagée du processus (équivalent du MEMORY global d'avant,
# mais encapsulée et avec une API claire).
memory = ConversationMemory()
