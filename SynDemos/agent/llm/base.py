"""
llm/base.py
===========
Interface abstraite d'un "provider" LLM.

But : aujourd'hui seul Ollama est branché, mais tout le reste du moteur
(planner, fsm, fix-loop) parle à cette interface, jamais directement à
httpx/Ollama. Ajouter Anthropic/OpenAI plus tard = ajouter une classe ici,
zéro changement ailleurs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class LLMResponse:
    """Forme normalisée de la réponse d'un provider, quel qu'il soit."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[list[dict[str, Any]]] = None,
        raw: Optional[dict[str, Any]] = None,
        thinking: str = "",
    ):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.raw = raw or {}
        # Texte de réflexion séparé (ex: <think>...</think> chez qwen3),
        # rempli uniquement par chat_stream(); vide si le modèle/provider
        # ne fait pas de réflexion visible ou via chat() non-stream.
        self.thinking = thinking


class StreamChunk:
    """
    Unité élémentaire d'un flux de streaming LLM.

    kind:
      - "thinking" : delta de texte de réflexion (ex: <think>...</think> chez qwen3)
      - "content"  : delta de texte de réponse finale
      - "tool_calls": liste complète des tool_calls (arrive en un seul chunk,
                      Ollama ne les streame pas token par token)
      - "done"     : fin du flux, contient la LLMResponse complète assemblée
    """

    __slots__ = ("kind", "text", "tool_calls", "response")

    def __init__(
        self,
        kind: str,
        text: str = "",
        tool_calls: Optional[list[dict[str, Any]]] = None,
        response: Optional["LLMResponse"] = None,
    ):
        self.kind = kind
        self.text = text
        self.tool_calls = tool_calls or []
        self.response = response


class LLMProvider(ABC):
    """Contrat que tout provider doit respecter."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Envoie une conversation et retourne une réponse normalisée (non-stream)."""
        raise NotImplementedError

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ):
        """
        Envoie une conversation et retourne un itérateur asynchrone de
        StreamChunk. Le dernier chunk émis est toujours kind="done" et
        porte la LLMResponse complète assemblée (content + tool_calls),
        pour que l'appelant n'ait pas à la reconstruire lui-même.
        """
        raise NotImplementedError

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Vérifie qu'un nom de modèle est valide pour ce provider."""
        raise NotImplementedError
