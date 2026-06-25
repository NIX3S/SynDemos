"""
core/planner.py
================
Construction du plan initial et des messages système.

Changements par rapport à l'ancien llm.py :
- le planner utilise désormais le mode JSON strict d'Ollama
  (`format: "json"`), donc on ne dépend plus uniquement d'un prompt qui
  "espère" du JSON avec un fallback `except: return plan vide` qui
  avalait silencieusement toute erreur de parsing.
- en cas d'échec malgré tout, l'erreur réelle est conservée dans le plan
  retourné (Plan.steps contient le message d'erreur) plutôt que de
  rendre un plan vide indistinguable d'un "rien à faire".
- le plan génère automatiquement une todo list (un TodoItem par step),
  affichée et mise à jour pendant l'exécution — comportement type
  Claude Code.
"""

from __future__ import annotations

import json
import logging
import uuid

from llm.base import LLMProvider
from llm.ollama_provider import LLMProviderError
from config import LLMConfig
from schemas import Plan, TodoItem

logger = logging.getLogger("agent.core.planner")


PLANNER_SYSTEM_PROMPT = """Tu es un planificateur d'agent autonome.

Tu dois produire UNIQUEMENT un objet JSON avec exactement cette forme :
{
  "need_code": true,
  "need_execution": true,
  "task_category": "code",
  "steps": ["étape 1", "étape 2", ...]
}

Règles :
- "steps" doit être une liste de courtes descriptions actionnables, dans l'ordre.
- "need_code" = true si la tâche nécessite d'écrire ou modifier du code.
- "need_execution" = true si du code généré doit être exécuté pour être validé.
- "task_category" classe la nature DOMINANTE de la demande, choisie parmi
  exactement ces 4 valeurs :
    "code"      -> écrire, corriger, déboguer ou exécuter du code
    "redaction" -> rédiger un texte original (article, email, documentation, README...)
    "synthese"  -> résumer, extraire ou reformuler un contenu existant (PDF, fichier, texte fourni)
    "reflexion" -> analyser, comparer, argumenter, raisonner sur un sujet sans produire de code ni de long texte
- Si la demande mélange plusieurs natures, choisis celle qui domine le travail réel à faire.
- Pas de texte hors du JSON. Pas de markdown. Pas de commentaire.
"""


def _build_planner_messages(prompt: str, memory_context: str) -> list[dict]:
    user_content = prompt
    if memory_context:
        user_content += f"\n\nContexte des échanges précédents:\n{memory_context}"

    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _todos_from_steps(steps: list[str]) -> list[TodoItem]:
    return [
        TodoItem(id=str(uuid.uuid4())[:8], label=step, status="pending")
        for step in steps
    ]


async def build_plan(
    provider: LLMProvider,
    prompt: str,
    memory_context: str = "",
    model: str | None = None,
) -> Plan:
    messages = _build_planner_messages(prompt, memory_context)

    try:
        response = await provider.chat(
            messages,
            tools=None,
            model=model or LLMConfig.MODEL_PLANNER,
            json_mode=True,
        )
    except LLMProviderError as e:
        logger.error("Echec d'appel LLM pendant le planning: %s", e)
        return Plan(
            need_code=False,
            need_execution=False,
            steps=[f"[ERREUR PLANNER] {e}"],
        )

    try:
        raw = json.loads(response.content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Plan non-JSON reçu du LLM: %s | contenu: %r", e, response.content[:300])
        return Plan(
            need_code=False,
            need_execution=False,
            steps=[f"[ERREUR PARSING PLAN] {e}"],
        )

    steps = raw.get("steps", []) or []
    task_category = _validate_task_category(raw.get("task_category"))

    return Plan(
        need_code=bool(raw.get("need_code", False)),
        need_execution=bool(raw.get("need_execution", False)),
        task_category=task_category,
        steps=steps,
        todos=_todos_from_steps(steps),
    )


def _validate_task_category(raw_category) -> str:
    """
    Le LLM peut renvoyer n'importe quoi dans task_category (faute de
    frappe, catégorie inventée, valeur manquante). On retombe sur "code"
    par défaut plutôt que de planter ou de propager une catégorie qui ne
    matchera jamais LLMConfig.MODEL_BY_CATEGORY — "code" est le choix le
    plus sûr car c'est le seul cas où une mauvaise classification a un
    coût visible immédiat (erreurs d'exécution détectées par verify_code),
    contrairement à redaction/synthese/reflexion qui échoueraient en silence.
    """
    if isinstance(raw_category, str) and raw_category in LLMConfig.TASK_CATEGORIES:
        return raw_category
    return "code"


def resolve_model_for_plan(plan: Plan, override: str | None = None) -> str:
    """
    Détermine le modèle Ollama à utiliser pour exécuter ce plan.

    Priorité :
      1. `override` (le client a explicitement demandé un modèle dans /ask)
      2. le modèle mappé à plan.task_category dans LLMConfig.MODEL_BY_CATEGORY
      3. LLMConfig.MODEL_EXEC en dernier recours

    L'override client garde la priorité absolue : le routage automatique
    est une aide par défaut, pas une contrainte — un client qui sait ce
    qu'il veut n'est jamais contredit par la classification du planner.
    """
    if override:
        return override
    return LLMConfig.MODEL_BY_CATEGORY.get(plan.task_category, LLMConfig.MODEL_EXEC)


AGENT_SYSTEM_PROMPT = """Tu es un agent autonome d'exécution.

OBJECTIF :
Résoudre entièrement la demande de l'utilisateur en utilisant les outils
disponibles.

OUTILS DISPONIBLES :
- write_file(path, content) : créer ou écraser un fichier
- edit_file(path, old_str, new_str) : remplacer une chaîne unique dans un fichier existant
- read_file(path) : lire un fichier
- list_dir(path) : lister un dossier
- shell(command) : exécuter une commande shell (python, pip, ls, cat, grep, find, pytest...)
- inspect_pdf(path) : connaître le nombre de pages d'un PDF et s'il contient du texte avant de l'extraire
- read_pdf(path, start_page, end_page) : extraire le texte d'un PDF du workspace

RÈGLES :
- Ne replanifie jamais : suis le plan fourni.
- N'utilise jamais de chemins absolus, uniquement relatifs au workspace.
- Préfère edit_file à write_file pour une petite correction sur un fichier existant.
- Exécute et corrige jusqu'à succès.
- Quand tout est terminé, réponds en texte clair sans appel d'outil.
"""


def build_agent_messages(prompt: str, plan: Plan, memory_context: str = "") -> list[dict]:
    user_content = (
        prompt
        + "\n\nPlan:\n"
        + json.dumps(plan.model_dump(), indent=2, ensure_ascii=False)
    )

    if memory_context:
        user_content += f"\n\nMémoire:\n{memory_context}"

    return [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
