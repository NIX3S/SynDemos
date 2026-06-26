"""
core/tool_runner.py
====================
Exécute les tool_calls retournés par le LLM, avec retry par outil,
et maintient le tracking des fichiers créés / diffs / outils appelés
sur le AgentContext.

Changement par rapport à l'ancien executor.py :
- le tracking de fichier ne fait plus planter le run si le LLM renvoie
  un chemin déjà absolu hors-workspace (l'ancien `p.relative_to(WORKSPACE)`
  levait une exception non interceptée dans ce cas précis) — on utilise
  désormais tools.sandbox.normalize_path qui est la SEULE source de
  vérité pour la résolution de chemin, partagée avec les outils eux-mêmes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from config import TOOL_RETRY_POLICY, WORKSPACE
from core.checkpoints import checkpoints, Checkpoint
from core.run_context import AgentContext, FileDiff
from tools.registry import get_tool
from tools.sandbox import normalize_path, PathSecurityError

logger = logging.getLogger("agent.core.tool_runner")


def _normalize_arguments(raw_args: Any, tool_name: str) -> dict[str, Any]:
    """
    Normalise les arguments d'un tool_call vers un dict, quelle que soit
    la forme renvoyée par le modèle. Observé en pratique avec Ollama
    (dépend du modèle, parfois même au sein d'une même session) :

    - dict déjà prêt à l'emploi (cas attendu/idéal) -> renvoyé tel quel
    - string JSON sérialisée (ex: '{"path": "a.py", "content": "..."}')
      -> parsée
    - liste (le modèle a halluciné une autre structure, ou un agrégat
      malformé de plusieurs appels) -> aucune façon fiable de la
      réinterpréter en arguments nommés ; on log et renvoie un dict
      vide plutôt que de planter toute la requête sur un crash non
      intercepté (`'list' object has no attribute 'get'`).
    - tout autre type inattendu -> même traitement défensif.
    """
    if isinstance(raw_args, dict):
        return raw_args

    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.error(
                "Arguments du tool_call '%s' sont une string non-JSON, impossible de les parser: %r",
                tool_name, raw_args[:200],
            )
            return {}
        if isinstance(parsed, dict):
            return parsed
        logger.error(
            "Arguments du tool_call '%s' sont une string JSON valide mais ne décodent pas vers un objet (type reçu: %s)",
            tool_name, type(parsed).__name__,
        )
        return {}

    logger.error(
        "Arguments du tool_call '%s' ont un type inattendu (%s), attendu dict ou string JSON. Valeur: %r",
        tool_name, type(raw_args).__name__, raw_args,
    )
    return {}


def call_tool_with_retry(name: str, args: dict[str, Any], run_id: Optional[str] = None) -> dict[str, Any]:
    fn = get_tool(name)
    if fn is None:
        return {"ok": False, "error": f"Outil inconnu: {name}"}

    # Injection silencieuse de run_id pour l'outil shell uniquement (lui
    # permet de s'enregistrer dans process_registry et d'être tué depuis
    # /stop pendant son exécution). Jamais exposé au LLM via le schéma
    # function-calling, ni accepté par les autres outils.
    call_args = dict(args)
    if name == "shell" and run_id:
        call_args["run_id"] = run_id

    retries = TOOL_RETRY_POLICY.get(name, 1)
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return fn(**call_args)
        except TypeError as e:
            # Typiquement : args mal formés (clé inattendue, type incompatible
            # avec la signature de l'outil) plutôt qu'une vraie erreur réseau/
            # fichier — on le rapporte distinctement pour aider au diagnostic.
            last_error = f"arguments invalides pour l'outil '{name}': {e}"
            logger.warning("TOOL RETRY (args invalides) : %s — %s", name, e)
        except Exception as e:  # un outil ne doit jamais faire planter le run
            last_error = str(e)
            logger.warning("TOOL RETRY : %s (tentative %d/%d): %s", name, attempt, retries, e)

    return {"ok": False, "error": last_error}


def _track_file_change(
    ctx: AgentContext, name: str, args: dict[str, Any], result: dict[str, Any]
) -> tuple[bool, Optional[Checkpoint]]:
    """
    Met à jour le tracking de fichiers du contexte ET enregistre un
    checkpoint (snapshot pré-modification) pour permettre l'undo.

    Retourne (is_code_file, checkpoint_ou_None). Le checkpoint n'est
    enregistré que si l'outil a réellement réussi (result["ok"] is True),
    pour ne jamais empiler un état qui ne correspond à aucune écriture
    réelle sur disque.
    """
    raw_path = args.get("path", "")
    if not raw_path:
        return False, None

    try:
        p = normalize_path(raw_path)
    except PathSecurityError:
        return False, None

    rel = str(p.relative_to(WORKSPACE))
    is_code_file = p.suffix == ".py"
    if is_code_file:
        ctx.created_files.add(rel)

    diff = result.get("diff")
    if diff:
        ctx.file_diffs.append(FileDiff(path=rel, diff=diff))

    checkpoint = None
    if result.get("ok"):
        new_content = (WORKSPACE / rel).read_text(encoding="utf-8") if (WORKSPACE / rel).exists() else ""
        checkpoint = checkpoints.record(
            run_id=ctx.run_id,
            rel_path=rel,
            previous_content=result.get("previous_content"),
            new_content=new_content,
            tool=name,
        )

    return is_code_file, checkpoint


def execute_tool_calls(
    ctx: AgentContext, tool_calls: list[dict[str, Any]]
) -> tuple[bool, list[dict[str, Any]], list[Checkpoint]]:
    """
    Exécute une liste de tool_calls renvoyés par le LLM.
    Retourne (code_generated, messages_a_ajouter_au_contexte_llm, checkpoints_crees).
    """
    results: list[dict[str, Any]] = []
    code_generated = False
    new_checkpoints: list[Checkpoint] = []

    for tc in tool_calls:
        name = tc["function"]["name"]
        args = _normalize_arguments(tc["function"].get("arguments"), name)

        result = call_tool_with_retry(name, args, run_id=ctx.run_id)

        if name in ("write_file", "edit_file"):
            is_code, checkpoint = _track_file_change(ctx, name, args, result)
            if is_code:
                code_generated = True
            if checkpoint:
                new_checkpoints.append(checkpoint)

        ctx.tools_called.append(name)
        results.append(
            {
                "role": "tool",
                "name": name,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    return code_generated, results, new_checkpoints
