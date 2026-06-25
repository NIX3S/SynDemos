"""
llm/ollama_provider.py
======================
Implémentation concrète du provider Ollama.

Corrige par rapport à l'ancien llm.py :
- gestion des erreurs réseau / HTTP (timeout, connexion refusée, status != 200)
- support du mode JSON strict d'Ollama (`format: "json"`) pour le planner,
  au lieu de compter sur un fallback regex fragile
- normalisation de la réponse en LLMResponse (le reste du code ne touche
  plus jamais à la forme brute du JSON Ollama)
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from config import LLMConfig
from llm.base import LLMProvider, LLMResponse, StreamChunk

logger = logging.getLogger("agent.llm.ollama")


class LLMProviderError(Exception):
    """Erreur remontée par un provider (réseau, parsing, modèle invalide...)."""


class _ThinkTagSplitter:
    """
    Sépare un flux de texte token par token en deltas "thinking" et
    "content" selon les balises <think>...</think> (qwen3 et consorts
    mélangent réflexion et réponse dans le même flux de contenu).

    Conçu pour être alimenté chunk par chunk via feed(), car une balise
    peut être coupée en plein milieu entre deux tokens reçus du réseau.
    """

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self._buffer = ""
        self._in_thinking = False

    def feed(self, token: str) -> list[tuple[str, str]]:
        """Retourne une liste de (kind, text) deltas à émettre pour ce token."""
        self._buffer += token
        out: list[tuple[str, str]] = []

        while True:
            tag = self.CLOSE_TAG if self._in_thinking else self.OPEN_TAG
            idx = self._buffer.find(tag)

            if idx == -1:
                # Pas de balise complète en vue : on ne peut émettre en sécurité
                # que la partie du buffer qui ne pourrait pas être un préfixe
                # de la balise recherchée.
                safe_len = self._longest_safe_prefix(self._buffer, tag)
                if safe_len > 0:
                    text = self._buffer[:safe_len]
                    self._buffer = self._buffer[safe_len:]
                    if text:
                        out.append(("thinking" if self._in_thinking else "content", text))
                break

            before = self._buffer[:idx]
            if before:
                out.append(("thinking" if self._in_thinking else "content", before))

            self._buffer = self._buffer[idx + len(tag):]
            self._in_thinking = not self._in_thinking

        return out

    @staticmethod
    def _longest_safe_prefix(buf: str, tag: str) -> int:
        """
        Longueur du préfixe de `buf` qu'on peut émettre sans risquer de
        couper une occurrence de `tag` qui serait en train d'arriver.
        """
        max_check = min(len(tag) - 1, len(buf))
        for size in range(max_check, 0, -1):
            if tag.startswith(buf[-size:]):
                return len(buf) - size
        return len(buf)

    def flush(self) -> list[tuple[str, str]]:
        """A appeler en fin de flux : tout ce qui reste dans le buffer est émis tel quel."""
        if not self._buffer:
            return []
        out = [("thinking" if self._in_thinking else "content", self._buffer)]
        self._buffer = ""
        return out


def _extract_thinking(raw_content: str) -> tuple[str, str]:
    """
    Sépare un contenu complet (non-streamé) en (thinking, content) en
    retirant les balises <think>...</think>. Utilisé par chat() pour
    rester cohérent avec ce que produit chat_stream().
    """
    thinking_parts: list[str] = []
    content_parts: list[str] = []
    remaining = raw_content

    while True:
        start = remaining.find(_ThinkTagSplitter.OPEN_TAG)
        if start == -1:
            content_parts.append(remaining)
            break

        content_parts.append(remaining[:start])
        remaining = remaining[start + len(_ThinkTagSplitter.OPEN_TAG):]

        end = remaining.find(_ThinkTagSplitter.CLOSE_TAG)
        if end == -1:
            # balise jamais fermée -> tout le reste compte comme réflexion
            thinking_parts.append(remaining)
            remaining = ""
            break

        thinking_parts.append(remaining[:end])
        remaining = remaining[end + len(_ThinkTagSplitter.CLOSE_TAG):]

    return "".join(thinking_parts), "".join(content_parts)


class OllamaProvider(LLMProvider):

    def __init__(
        self,
        host: Optional[str] = None,
        default_model: Optional[str] = None,
        allowed_models: Optional[list[str]] = None,
        timeout: Optional[int] = None,
    ):
        self.chat_url = f"{host or LLMConfig.OLLAMA_HOST}/api/chat"
        self.default_model = default_model or LLMConfig.MODEL_EXEC
        self.allowed_models = set(allowed_models or LLMConfig.ALLOWED_MODELS)
        self.timeout = timeout or LLMConfig.REQUEST_TIMEOUT

    def supports_model(self, model: str) -> bool:
        return model in self.allowed_models

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        chosen_model = model or self.default_model

        if not self.supports_model(chosen_model):
            raise LLMProviderError(
                f"Modèle non autorisé: '{chosen_model}'. "
                f"Modèles autorisés: {sorted(self.allowed_models)}"
            )

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.chat_url, json=payload)
        except httpx.ConnectError as e:
            raise LLMProviderError(
                f"Impossible de joindre Ollama sur {self.chat_url} "
                f"(le service est-il lancé ? `ollama serve`). Détail: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMProviderError(
                f"Timeout après {self.timeout}s en attendant Ollama."
            ) from e
        except httpx.HTTPError as e:
            raise LLMProviderError(f"Erreur HTTP vers Ollama: {e}") from e

        if resp.status_code != 200:
            raise LLMProviderError(
                f"Ollama a retourné HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise LLMProviderError(f"Réponse Ollama non-JSON: {e}") from e

        message = data.get("message", {})
        raw_content = message.get("content", "")
        thinking, content = _extract_thinking(raw_content)
        tool_calls = message.get("tool_calls") or []

        return LLMResponse(content=content, tool_calls=tool_calls, raw=data, thinking=thinking)

    async def list_models(self) -> list[str]:
        """Interroge Ollama pour la liste réelle des modèles installés."""
        tags_url = self.chat_url.replace("/api/chat", "/api/tags")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(tags_url)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError as e:
            logger.warning("Impossible de lister les modèles Ollama: %s", e)
            return []

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Version streamée de chat(). Ollama renvoie du NDJSON (une ligne JSON
        par chunk) quand stream=True. Chaque ligne contient un delta dans
        message.content, et le tout dernier objet a "done": true.

        On sépare thinking/content au fil de l'eau via _ThinkTagSplitter,
        et on assemble une LLMResponse complète émise en dernier chunk
        (kind="done") pour que l'appelant garde la même interface qu'avec
        chat() une fois le flux terminé.
        """
        chosen_model = model or self.default_model

        if not self.supports_model(chosen_model):
            raise LLMProviderError(
                f"Modèle non autorisé: '{chosen_model}'. "
                f"Modèles autorisés: {sorted(self.allowed_models)}"
            )

        payload: dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        splitter = _ThinkTagSplitter()
        full_content_parts: list[str] = []
        full_thinking_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        last_raw: dict[str, Any] = {}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.chat_url, json=payload) as resp:

                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise LLMProviderError(
                            f"Ollama a retourné HTTP {resp.status_code}: {body[:500]!r}"
                        )

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Ligne NDJSON Ollama invalide ignorée: %r", line[:200])
                            continue

                        last_raw = chunk
                        message = chunk.get("message", {})
                        delta_text = message.get("content", "")
                        delta_tool_calls = message.get("tool_calls") or []

                        if delta_tool_calls:
                            tool_calls.extend(delta_tool_calls)
                            yield StreamChunk(kind="tool_calls", tool_calls=delta_tool_calls)

                        if delta_text:
                            for kind, text in splitter.feed(delta_text):
                                if kind == "thinking":
                                    full_thinking_parts.append(text)
                                else:
                                    full_content_parts.append(text)
                                yield StreamChunk(kind=kind, text=text)

                        if chunk.get("done"):
                            break

        except httpx.ConnectError as e:
            raise LLMProviderError(
                f"Impossible de joindre Ollama sur {self.chat_url} "
                f"(le service est-il lancé ? `ollama serve`). Détail: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMProviderError(f"Timeout après {self.timeout}s en attendant Ollama.") from e
        except httpx.HTTPError as e:
            raise LLMProviderError(f"Erreur HTTP vers Ollama: {e}") from e

        for kind, text in splitter.flush():
            if kind == "thinking":
                full_thinking_parts.append(text)
            else:
                full_content_parts.append(text)
            yield StreamChunk(kind=kind, text=text)

        final_response = LLMResponse(
            content="".join(full_content_parts),
            tool_calls=tool_calls,
            raw=last_raw,
        )
        final_response.thinking = "".join(full_thinking_parts)

        yield StreamChunk(kind="done", response=final_response)
