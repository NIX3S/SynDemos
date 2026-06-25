"""
core/verifier.py
=================
Vérifie que les fichiers Python créés pendant le run s'exécutent sans
erreur, et pilote la boucle de correction (fix loop) si besoin.

Remplace à la fois l'ancien verifier.py (qui définissait verify_code/
execute_all_python mais n'était plus jamais importé) et la version
dupliquée dans executor.py qui le shadowait. Une seule implémentation
maintenant, utilisée par le FSM.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from config import WORKSPACE, RetryPolicy
from core.checkpoints import Checkpoint
from core.run_context import AgentContext
from llm.base import LLMProvider, LLMResponse
from llm.ollama_provider import LLMProviderError
from tools.registry import get_tool, all_tool_schemas

logger = logging.getLogger("agent.core.verifier")


@dataclass
class FixEvent:
    """Evénement émis pendant la boucle de correction (auto_fix)."""

    kind: str  # "thinking" | "content" | "checkpoint"
    text: str = ""
    checkpoint: Optional[Checkpoint] = None


def run_python_files(ctx: AgentContext) -> list[dict]:
    """Exécute chaque .py créé pendant le run et collecte le résultat."""
    shell = get_tool("shell")
    results = []

    for rel_path in sorted(ctx.created_files):
        file_on_disk = WORKSPACE / rel_path
        if not file_on_disk.exists():
            continue

        result = shell(f"python {rel_path}", run_id=ctx.run_id)
        results.append({"file": rel_path, "result": result})

    return results


def verify_code(ctx: AgentContext) -> tuple[bool, list[dict]]:
    """
    Retourne (ok, erreurs).
    ok=True si aucun fichier créé (rien à vérifier) ou si tous s'exécutent
    avec un code de retour 0.
    """
    executions = run_python_files(ctx)

    if not executions:
        return True, []

    errors = [e for e in executions if not e["result"].get("ok", e["result"].get("code") == 0)]
    return len(errors) == 0, errors


async def auto_fix(
    provider: LLMProvider,
    ctx: AgentContext,
    model: str | None = None,
) -> AsyncIterator[Any]:
    """
    Boucle de correction : tant qu'il y a des erreurs et qu'on n'a pas
    dépassé MAX_FIX_ATTEMPTS, on redonne les erreurs au LLM et on
    exécute les tool_calls qu'il propose.

    Générateur asynchrone : yield des FixEvent (thinking/content/checkpoint)
    au fil de l'eau, et se termine en ayant mis ctx.fix_result à True/False
    (l'appelant lit cette valeur après avoir épuisé le générateur, comme
    pour récupérer un "retour" d'un générateur Python classique).
    """
    from core.tool_runner import execute_tool_calls  # import tardif anti-cycle

    ctx.fix_result = False

    for _ in range(RetryPolicy.MAX_FIX_ATTEMPTS):
        if ctx.stop_requested:
            yield FixEvent(kind="stopped")
            return

        ok, errors = verify_code(ctx)

        if ok:
            ctx.fix_result = True
            return

        ctx.messages.append(
            {
                "role": "user",
                "content": "Corrige ces erreurs:\n" + json.dumps(errors, indent=2, ensure_ascii=False),
            }
        )

        made_tool_call = False

        for _ in range(3):
            if ctx.stop_requested:
                yield FixEvent(kind="stopped")
                return

            final_response: Optional[LLMResponse] = None

            try:
                async for chunk in provider.chat_stream(ctx.messages, tools=all_tool_schemas(), model=model):
                    if ctx.stop_requested:
                        yield FixEvent(kind="stopped")
                        return
                    if chunk.kind in ("thinking", "content"):
                        yield FixEvent(kind=chunk.kind, text=chunk.text)
                    elif chunk.kind == "done":
                        final_response = chunk.response
            except LLMProviderError as e:
                logger.error("Echec LLM pendant le fix loop: %s", e)
                ctx.error = str(e)
                ctx.fix_result = False
                return

            if final_response is None:
                ctx.error = "Flux LLM interrompu pendant le fix loop"
                ctx.fix_result = False
                return

            ctx.messages.append({"role": "assistant", "content": final_response.content})

            if not final_response.tool_calls:
                break

            made_tool_call = True
            _, tool_msgs, new_checkpoints = execute_tool_calls(ctx, final_response.tool_calls)
            ctx.messages.extend(tool_msgs)

            for cp in new_checkpoints:
                yield FixEvent(kind="checkpoint", checkpoint=cp)

        if not made_tool_call:
            # le LLM n'a rien proposé de concret -> pas la peine de boucler indéfiniment
            break

    ok, _ = verify_code(ctx)
    ctx.fix_result = ok
