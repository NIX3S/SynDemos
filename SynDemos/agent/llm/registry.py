"""
llm/registry.py
================
Point d'entrée unique pour obtenir un provider LLM configuré.

Ollama est le seul provider actif par défaut, et c'est volontaire : tout
provider externe (API payante, données envoyées hors de la machine de
l'utilisateur) est bloqué tant que la personne ne l'active pas
explicitement via AGENT_ALLOW_EXTERNAL_PROVIDERS=true dans sa config.
Sans ce flag, demander un provider autre que "ollama" échoue avec un
message clair plutôt que d'appeler silencieusement une API externe.

Pour le multi-modèle SANS sortir d'Ollama (plusieurs modèles qwen3/llama
selon la tâche), voir LLMConfig.MODEL_BY_CATEGORY dans config.py — ça ne
passe pas par ce flag, c'est toujours Ollama, juste un modèle différent.
"""

from __future__ import annotations

from functools import lru_cache

from config import LLMConfig
from llm.base import LLMProvider
from llm.ollama_provider import OllamaProvider


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    if LLMConfig.PROVIDER == "ollama":
        return OllamaProvider()

    if not LLMConfig.ALLOW_EXTERNAL_PROVIDERS:
        raise NotImplementedError(
            f"Provider LLM '{LLMConfig.PROVIDER}' demandé, mais les providers "
            "externes sont désactivés (AGENT_ALLOW_EXTERNAL_PROVIDERS=false par "
            "défaut). Mets AGENT_ALLOW_EXTERNAL_PROVIDERS=true dans ta config si "
            "tu veux explicitement autoriser un appel à une API externe."
        )

    raise NotImplementedError(
        f"Provider LLM inconnu ou pas encore implémenté: '{LLMConfig.PROVIDER}'. "
        "Seul 'ollama' est implémenté à ce jour."
    )
