"""
tools/registry.py
==================
Registre central des outils exposés au LLM.

Chaque outil :
- est une fonction Python pure (testable indépendamment)
- s'enregistre via le décorateur @tool("nom")
- doit retourner un dict JSON-sérialisable

Le schéma JSON exposé au LLM (TOOLS) est défini ici à côté du registre
pour qu'ajouter un outil = un seul endroit à toucher, au lieu d'avoir
le schéma dans un fichier et l'implémentation dans un autre comme avant.
"""

from __future__ import annotations

from typing import Any, Callable

TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {}
TOOL_SCHEMAS: list[dict[str, Any]] = []


def tool(name: str, schema: dict[str, Any]):
    """
    Décorateur : enregistre une fonction comme outil utilisable par le LLM
    et déclare son schéma JSON (function-calling) en même temps.
    """

    def wrapper(fn: Callable[..., dict[str, Any]]):
        TOOL_REGISTRY[name] = fn
        TOOL_SCHEMAS.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    **schema,
                },
            }
        )
        return fn

    return wrapper


def get_tool(name: str) -> Callable[..., dict[str, Any]] | None:
    return TOOL_REGISTRY.get(name)


def all_tool_schemas() -> list[dict[str, Any]]:
    return TOOL_SCHEMAS
