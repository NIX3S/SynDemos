"""
config.py
=========
Configuration centralisée de l'agent.

Tout ce qui est "réglable" passe par des variables d'environnement avec
valeurs par défaut sensées. Rien n'est codé en dur ailleurs dans le projet :
si un module a besoin d'un chemin, d'un modèle ou d'une limite, il vient
le lire ici.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Workspace : LE seul endroit où ce chemin est défini dans tout le projet.
# ---------------------------------------------------------------------------
WORKSPACE: Path = Path(
    os.getenv("AGENT_WORKSPACE", "/workspace/workforce")
).resolve()

LOG_DIR: Path = WORKSPACE / "logs" / "runs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

VENV: Path = Path(os.getenv("AGENT_VENV", str(WORKSPACE / ".venv")))


# ---------------------------------------------------------------------------
# LLM / Providers
# ---------------------------------------------------------------------------
class LLMConfig:
    # Provider actif. "ollama" par défaut, et c'est volontaire : tout le
    # traitement reste local à la machine de l'utilisateur, rien n'est
    # envoyé à un service externe sauf décision explicite (voir
    # ALLOW_EXTERNAL_PROVIDERS ci-dessous).
    PROVIDER: str = os.getenv("AGENT_LLM_PROVIDER", "ollama")

    # Garde de sécurité : tant que ce flag est False (défaut), demander un
    # provider autre que "ollama" échoue immédiatement avec un message
    # clair plutôt que d'appeler silencieusement une API externe (coût,
    # données envoyées hors de la machine). La personne doit explicitement
    # mettre AGENT_ALLOW_EXTERNAL_PROVIDERS=true pour débloquer ça.
    # Aucun provider externe n'est implémenté à ce jour dans ce projet —
    # ce flag prépare le terrain pour en ajouter un plus tard sans risquer
    # qu'il soit activé par accident.
    ALLOW_EXTERNAL_PROVIDERS: bool = _env_bool("AGENT_ALLOW_EXTERNAL_PROVIDERS", False)

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_CHAT_URL: str = f"{OLLAMA_HOST}/api/chat"

    # Modèle utilisé par défaut pour les tâches d'exécution (agent).
    MODEL_EXEC: str = os.getenv("AGENT_MODEL_EXEC", "qwen3:8b")

    # Modèle utilisé pour le planning (peut être plus léger/rapide).
    MODEL_PLANNER: str = os.getenv("AGENT_MODEL_PLANNER", MODEL_EXEC)

    # Routage automatique par catégorie de tâche : le planner classe la
    # demande (code / redaction / synthese / reflexion) et ce mapping
    # choisit le modèle Ollama le plus adapté pour exécuter cette tâche
    # précise, sans que le client ait besoin de le spécifier lui-même.
    # Chaque catégorie retombe sur MODEL_EXEC si elle n'est pas surchargée
    # en env, donc un déploiement minimal sans aucune variable additionnelle
    # continue de fonctionner exactement comme avant (un seul modèle pour tout).
    # Tout ceci reste strictement DANS Ollama : changer de catégorie change
    # de modèle qwen3/llama local, jamais de provider externe.
    MODEL_BY_CATEGORY: dict[str, str] = {
        "code": os.getenv("AGENT_MODEL_CODE", MODEL_EXEC),
        "redaction": os.getenv("AGENT_MODEL_REDACTION", MODEL_EXEC),
        "synthese": os.getenv("AGENT_MODEL_SYNTHESE", MODEL_EXEC),
        "reflexion": os.getenv("AGENT_MODEL_REFLEXION", MODEL_EXEC),
    }
    TASK_CATEGORIES: tuple[str, ...] = tuple(MODEL_BY_CATEGORY.keys())

    # Modèles autorisés que le client peut demander via l'API (sécurité :
    # on n'exécute pas n'importe quel nom de modèle envoyé par le client).
    # Inclut automatiquement tous les modèles du mapping par catégorie,
    # pour qu'un modèle configuré pour le routage ne soit jamais
    # silencieusement refusé faute d'avoir été dupliqué dans cette liste.
    ALLOWED_MODELS: list[str] = list(
        dict.fromkeys(
            _env_list(
                "AGENT_ALLOWED_MODELS",
                [MODEL_EXEC, MODEL_PLANNER, "qwen3:8b", "Coder", "Reasoning"],
            )
            + list(MODEL_BY_CATEGORY.values())
        )
    )

    REQUEST_TIMEOUT: int = _env_int("AGENT_LLM_TIMEOUT", 120)

    # On force Ollama à répondre en JSON strict pour le planner.
    JSON_FORMAT_SUPPORTED: bool = True


# ---------------------------------------------------------------------------
# Politique de retry / limites d'exécution
# ---------------------------------------------------------------------------
class RetryPolicy:
    MAX_STEPS: int = _env_int("AGENT_MAX_STEPS", 30)
    MAX_FIX_ATTEMPTS: int = _env_int("AGENT_MAX_FIX_ATTEMPTS", 5)
    MAX_VERIFY_ATTEMPTS: int = _env_int("AGENT_MAX_VERIFY_ATTEMPTS", 5)
    MAX_TOOL_CALLS_PER_STEP: int = _env_int("AGENT_MAX_TOOLS_PER_STEP", 25)


TOOL_RETRY_POLICY: dict[str, int] = {
    "shell": 3,
    "write_file": 2,
    "read_file": 2,
    "edit_file": 2,
    "list_dir": 2,
}


# ---------------------------------------------------------------------------
# Sécurité shell
# ---------------------------------------------------------------------------
FORBIDDEN_SUBSTRINGS: list[str] = [
    "rm -rf",
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    ":(){:|:&};:",
    "> /dev/sda",
    "dd if=",
]

ALLOWED_COMMANDS: set[str] = {
    "ls", "pwd", "cat", "grep", "find",
    "python", "python3", "pip", "pip3",
    "mkdir", "echo", "head", "tail", "wc",
    "pytest", "ruff", "black",
}

COMMAND_ALIASES: dict[str, str] = {
    "python3": "python",
    "python3.12": "python",
    "pip3": "pip",
}

SHELL_DEFAULT_TIMEOUT: int = _env_int("AGENT_SHELL_TIMEOUT", 120)
SHELL_PIP_TIMEOUT: int = _env_int("AGENT_SHELL_PIP_TIMEOUT", 300)


# ---------------------------------------------------------------------------
# Mémoire conversationnelle (mémoire courte, en RAM)
# ---------------------------------------------------------------------------
MEMORY_MAX_TURNS: int = _env_int("AGENT_MEMORY_MAX_TURNS", 5)


# ---------------------------------------------------------------------------
# Types d'événements émis par le moteur (contrat avec le frontend / SSE)
# ---------------------------------------------------------------------------
EVENT_TYPES: set[str] = {
    "start",
    "plan",
    "todo_update",
    "exec",
    "thinking_delta",
    "content_delta",
    "tool_call",
    "tool_result",
    "fallback",
    "verify",
    "fix_start",
    "fix_done",
    "stopped",
    "max_steps",
    "final",
    "error",
    "checkpoint",
    "undo",
}


# ---------------------------------------------------------------------------
# Etats de la FSM
# ---------------------------------------------------------------------------
class State:
    EXEC = "EXEC"
    VERIFY = "VERIFY"
    FIX = "FIX"
    DONE = "DONE"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
