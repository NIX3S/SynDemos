"""
core/engine.py
===============
Moteur FSM principal de l'agent. Remplace executor.py.

Bugs corrigés par rapport à l'ancien executor.py :
- La transition EXEC -> VERIFY ne se déclenchait que si
  `plan.need_execution AND created_files` étaient vrais simultanément.
  Si le planner répondait need_execution=false alors que du code venait
  d'être écrit (ce qui arrive — le planner peut se tromper), la
  vérification était silencieusement sautée et le run finissait "DONE"
  sans jamais exécuter le code généré. Ici : dès qu'un fichier .py a été
  créé, on vérifie, peu importe ce que disait le plan.
- `regex_tool` (fallback par regex sur le texte brut) est supprimé : le
  planner et l'agent utilisent maintenant le JSON mode natif d'Ollama
  et le function-calling structuré, donc ce filet de sécurité fragile
  n'est plus nécessaire et ne masque plus de vrais bugs de parsing.
- Le plan génère une todo list, mise à jour ("in_progress"/"done") au
  fil de l'exécution et streamée au client via l'event "todo_update" —
  visibilité façon Claude Code sur l'avancement réel du run.
- Toutes les erreurs LLM sont désormais des LLMProviderError explicites
  (message clair : Ollama down, modèle interdit, timeout...) au lieu
  d'exceptions génériques remontant tel quel.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from config import RetryPolicy
from core.events import emit
from core.memory import memory
from core.planner import build_agent_messages, build_plan, resolve_model_for_plan
from core.run_context import AgentContext, State
from core.tool_runner import execute_tool_calls
from core.verifier import auto_fix, verify_code
from llm.base import LLMProvider
from llm.ollama_provider import LLMProviderError
from llm.registry import get_provider
from schemas import AskRequest
from storage.runs import runs
from tools.registry import all_tool_schemas

logger = logging.getLogger("agent.core.engine")


def _mark_progress(ctx: AgentContext) -> None:
    """Avance la todo list d'un cran : le premier 'pending' devient 'in_progress',
    sauf s'il y en a déjà un in_progress (on ne le redéclare pas)."""
    if any(t.status == "in_progress" for t in ctx.todos):
        return
    nxt = ctx.next_pending_todo()
    if nxt:
        ctx.mark_todo(nxt.id, "in_progress")


def _complete_current_todo(ctx: AgentContext, success: bool = True) -> None:
    for t in ctx.todos:
        if t.status == "in_progress":
            ctx.mark_todo(t.id, "done" if success else "failed")
            return


async def run_ask_stream(req: AskRequest) -> AsyncIterator[str]:
    provider: LLMProvider = get_provider()
    client_override = req.model

    if client_override and not provider.supports_model(client_override):
        # on ne fait pas confiance à un nom de modèle arbitraire venu du client
        client_override = None

    # Le planner utilise toujours le même modèle stable (MODEL_PLANNER, ou
    # l'override client) — il ne doit pas dépendre de la catégorie qu'il
    # est lui-même en train de déterminer, ce serait circulaire.
    plan = await build_plan(provider, req.prompt, memory.build_context(), model=client_override)

    # Le modèle d'EXÉCUTION, lui, est routé automatiquement selon la
    # catégorie de tâche détectée par le planner (code/redaction/synthese/
    # reflexion) via LLMConfig.MODEL_BY_CATEGORY — sauf si le client a
    # explicitement demandé un modèle, qui garde toujours la priorité.
    exec_model = resolve_model_for_plan(plan, override=client_override)

    ctx = AgentContext(prompt=req.prompt, plan=plan)
    ctx.todos = plan.todos
    ctx.model_used = exec_model
    runs.register(ctx)

    ctx.messages = build_agent_messages(req.prompt, plan, memory.build_context())

    yield emit(ctx, "start", {"prompt": ctx.prompt})
    yield emit(ctx, "plan", {**plan.model_dump(), "model_used": exec_model})
    if ctx.todos:
        yield emit(ctx, "todo_update", ctx.todos_as_dicts())

    final_answer = "Terminé."

    try:
        async for event_line in _main_loop(ctx, provider, exec_model):
            yield event_line

        final_answer = _build_final_answer(ctx)

    finally:
        memory.update(req.prompt, final_answer)
        yield emit(
            ctx,
            "final",
            {"answer": final_answer, "tools": ctx.tools_called, "state": ctx.state},
        )
        runs.archive(ctx.run_id)


async def _main_loop(
    ctx: AgentContext, provider: LLMProvider, model: str | None
) -> AsyncIterator[str]:

    while ctx.state not in (State.DONE, State.STOPPED):

        if ctx.stop_requested:
            ctx.state = State.STOPPED
            yield emit(ctx, "stopped")
            return

        if ctx.step >= RetryPolicy.MAX_STEPS:
            ctx.state = State.DONE
            yield emit(ctx, "max_steps")
            return

        ctx.step += 1

        if ctx.state == State.EXEC:
            async for line in _step_exec(ctx, provider, model):
                yield line

        elif ctx.state == State.VERIFY:
            async for line in _step_verify(ctx, provider, model):
                yield line

        elif ctx.state == State.FIX:
            async for line in _step_fix(ctx, provider, model):
                yield line

        else:
            ctx.state = State.DONE


async def _step_exec(
    ctx: AgentContext, provider: LLMProvider, model: str | None
) -> AsyncIterator[str]:
    _mark_progress(ctx)
    if ctx.todos:
        yield emit(ctx, "todo_update", ctx.todos_as_dicts())

    final_response = None

    try:
        async for chunk in provider.chat_stream(ctx.messages, tools=all_tool_schemas(), model=model):
            if ctx.stop_requested:
                ctx.state = State.STOPPED
                yield emit(ctx, "stopped", {"during": "exec_stream"})
                return

            if chunk.kind == "thinking":
                yield emit(ctx, "thinking_delta", {"text": chunk.text})
            elif chunk.kind == "content":
                yield emit(ctx, "content_delta", {"text": chunk.text})
            elif chunk.kind == "done":
                final_response = chunk.response
            # kind == "tool_calls" : on attend le chunk "done" qui porte
            # la liste complète assemblée, pas la peine de streamer ça token
            # par token (Ollama les envoie déjà groupés, pas incrémentaux).

    except LLMProviderError as e:
        ctx.error = str(e)
        ctx.state = State.DONE
        yield emit(ctx, "error", {"source": "llm", "error": str(e)})
        return

    if ctx.stop_requested:
        ctx.state = State.STOPPED
        yield emit(ctx, "stopped", {"during": "exec_stream"})
        return

    if final_response is None:
        ctx.error = "Flux LLM interrompu sans chunk final"
        ctx.state = State.DONE
        yield emit(ctx, "error", {"source": "llm", "error": ctx.error})
        return

    ctx.messages.append({"role": "assistant", "content": final_response.content})

    yield emit(
        ctx,
        "exec",
        {
            "content": final_response.content,
            "thinking": final_response.thinking,
            "tools": final_response.tool_calls,
        },
    )

    if final_response.tool_calls:
        code_generated, tool_msgs, new_checkpoints = execute_tool_calls(ctx, final_response.tool_calls)
        ctx.messages.extend(tool_msgs)
        yield emit(ctx, "tool_result", ctx.tools_called[-10:])

        for cp in new_checkpoints:
            yield emit(ctx, "checkpoint", {"rel_path": cp.rel_path, "tool": cp.tool, "timestamp": cp.timestamp})
    else:
        code_generated = False

    # Transition :
    # - si le LLM vient encore d'appeler des outils, on reste en EXEC pour
    #   lui laisser continuer sa séquence (ex: créer plusieurs fichiers liés
    #   d'affilée) — passer en VERIFY après CHAQUE tool_call individuel
    #   interromprait une création multi-fichiers en plein milieu.
    # - seulement quand le LLM n'appelle plus aucun outil (il considère son
    #   tour terminé) ET qu'au moins un .py a été créé/modifié à un moment
    #   du run, on vérifie — qu'importe ce que disait le plan initial sur
    #   need_execution.
    if not final_response.tool_calls:
        if ctx.created_files:
            ctx.state = State.VERIFY
        else:
            _complete_current_todo(ctx, success=True)
            if ctx.todos:
                yield emit(ctx, "todo_update", ctx.todos_as_dicts())
            ctx.state = State.DONE


async def _step_verify(
    ctx: AgentContext, provider: LLMProvider, model: str | None
) -> AsyncIterator[str]:
    ctx.execution_attempts += 1

    if ctx.execution_attempts > RetryPolicy.MAX_VERIFY_ATTEMPTS:
        ctx.state = State.DONE
        yield emit(ctx, "verify", {"ok": False, "attempts": ctx.execution_attempts, "reason": "max_attempts"})
        return

    ok, errors = verify_code(ctx)

    yield emit(ctx, "verify", {"ok": ok, "attempts": ctx.execution_attempts, "errors": errors})

    _complete_current_todo(ctx, success=ok)
    if ctx.todos:
        yield emit(ctx, "todo_update", ctx.todos_as_dicts())

    ctx.state = State.DONE if ok else State.FIX


async def _step_fix(
    ctx: AgentContext, provider: LLMProvider, model: str | None
) -> AsyncIterator[str]:
    ctx.fix_attempts += 1
    yield emit(ctx, "fix_start", {"attempt": ctx.fix_attempts})

    async for fix_event in auto_fix(provider, ctx, model=model):
        if fix_event.kind == "stopped":
            ctx.state = State.STOPPED
            yield emit(ctx, "stopped", {"during": "fix_loop"})
            return
        elif fix_event.kind == "thinking":
            yield emit(ctx, "thinking_delta", {"text": fix_event.text})
        elif fix_event.kind == "content":
            yield emit(ctx, "content_delta", {"text": fix_event.text})
        elif fix_event.kind == "checkpoint" and fix_event.checkpoint:
            cp = fix_event.checkpoint
            yield emit(ctx, "checkpoint", {"rel_path": cp.rel_path, "tool": cp.tool, "timestamp": cp.timestamp})

    yield emit(ctx, "fix_done", {"fixed": ctx.fix_result})

    ctx.state = State.VERIFY


def _build_final_answer(ctx: AgentContext) -> str:
    for msg in reversed(ctx.messages):
        if msg.get("role") == "assistant":
            content = (msg.get("content") or "").strip()
            if content:
                return content
    if ctx.error:
        return f"Le run s'est arrêté sur une erreur: {ctx.error}"
    return "Terminé."
