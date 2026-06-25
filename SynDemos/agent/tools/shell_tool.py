"""
tools/shell_tool.py
====================
Exécution de commandes shell, bornée au WORKSPACE.

Bugs corrigés par rapport à l'ancien tools.py :
- `WORKSPACE` était ré-importé puis ré-écrasé en dur juste après
  l'import de configuration.py -> toute la sécurité de chemin reposait
  sur une valeur qui ignorait silencieusement la config. Ici WORKSPACE
  vient uniquement de config.py, jamais réécrit.
- `timeout = None if cmd == "pip"` faisait tourner `pip` SANS AUCUNE
  LIMITE de temps (un pip install qui plante peut bloquer le run pour
  toujours). Remplacé par un timeout long mais fini, dédié à pip.
- Capture des prints de debug supprimée (print("step1")...) au profit
  d'un logger standard, désactivable.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from config import WORKSPACE, VENV, SHELL_DEFAULT_TIMEOUT, SHELL_PIP_TIMEOUT
from tools import process_registry
from tools.registry import tool
from tools.sandbox import validate_command, CommandSecurityError

logger = logging.getLogger("agent.tools.shell")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}


def _kill_process_group(proc: subprocess.Popen) -> None:
    """
    Tue tout le groupe de processus de `proc`, pas seulement son PID.
    Nécessaire car `command` tourne via `shell=True` : proc.kill() seul
    ne tuerait que /bin/sh, laissant son enfant réel (ex: python lancé
    par le shell) continuer à tourner en arrière-plan, reparenté à init.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass  # déjà mort


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(VENV)
    env["PATH"] = f"{VENV}/bin:" + env.get("PATH", "")
    env["MPLBACKEND"] = "Agg"  # matplotlib headless
    return env


def _resolve_timeout(command: str) -> int:
    head = command.strip().split()[0] if command.strip() else ""
    if head in ("pip", "pip3"):
        return SHELL_PIP_TIMEOUT
    return SHELL_DEFAULT_TIMEOUT


POLL_INTERVAL = 0.5  # secondes entre deux vérifications proc.poll()


def _wait_with_polling(
    proc: subprocess.Popen,
    timeout: int,
    run_id: str | None,
    is_protected: bool,
) -> bool:
    """
    Attend la fin de `proc` par polling plutôt que par un communicate()
    bloquant. Retourne True si on doit considérer ça comme un timeout
    interne (donc tuer le process), False si le process s'est terminé
    (normalement, ou parce qu'il a été tué de l'extérieur via /stop
    force=True — proc.poll() le détecte naturellement dans les deux cas,
    pas besoin de vérifier process_registry ici).

    Pour une commande protégée (pip install...) : une fois le timeout
    normal dépassé, on continue d'attendre indéfiniment. C'est
    /stop?force=true qui, via process_registry.kill(), tue le process
    directement — ce qui fait sortir cette boucle au prochain poll(),
    pas un timeout interne. Donc un `pip install scikit-learn` qui
    prend 4 minutes va au bout sans qu'aucun timeout ne le coupe.
    """
    elapsed = 0.0

    while True:
        if proc.poll() is not None:
            return False  # terminé (normalement, ou tué via /stop force=true)

        if elapsed >= timeout and not is_protected:
            return True  # timeout réel pour une commande non protégée

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL


@tool(
    "shell",
    {
        "description": (
            "Exécuter une commande shell dans le workspace. "
            "Commandes autorisées uniquement (python, pip, ls, cat, grep, "
            "find, pytest...). Pas de sudo, pas de suppression destructive."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
)
def shell(command: str, run_id: str | None = None) -> dict[str, Any]:
    """
    run_id (optionnel, injecté par tool_runner — jamais exposé au LLM dans
    le schéma function-calling ci-dessus) : permet d'enregistrer le
    process dans tools.process_registry pour qu'il puisse être tué
    depuis l'endpoint /stop/{run_id} pendant son exécution.

    Implémentation par polling (proc.poll() + petits sleeps) plutôt que
    proc.communicate(timeout=...) bloquant : nécessaire pour qu'une
    commande "protégée" (pip install...) puisse attendre au-delà du
    timeout normal sans jamais être tuée tant qu'aucune confirmation
    explicite (force=True sur /stop) n'est arrivée — voir
    tools/process_registry.py pour la logique de protection.
    """
    try:
        command = validate_command(command)
    except CommandSecurityError as e:
        return {"ok": False, "error": str(e)}

    env = _build_env()
    timeout = _resolve_timeout(command)
    is_protected = command.strip().startswith(process_registry.PROTECTED_COMMAND_PREFIXES)

    before = set(WORKSPACE.rglob("*"))

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(WORKSPACE),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # nouveau groupe de process : nécessaire pour
            # pouvoir tuer le process ENFANT (ex: python lancé par le shell) via
            # process_registry.kill(), pas seulement le shell parent. Sans ça,
            # proc.kill() tue /bin/sh mais le vrai process continue de tourner
            # en arrière-plan jusqu'à sa fin naturelle.
        )

        if run_id:
            process_registry.register(run_id, proc, command)

        timed_out = _wait_with_polling(proc, timeout, run_id, is_protected)

        if timed_out:
            _kill_process_group(proc)
            stdout, stderr = proc.communicate()
            return {
                "ok": False,
                "error": f"timeout après {timeout}s",
                "stdout": stdout,
                "stderr": stderr,
            }

        stdout, stderr = proc.communicate()
        returncode = proc.returncode

    except Exception as e:  # garde-fou : ne jamais laisser planter le run
        logger.exception("Erreur shell inattendue")
        return {"ok": False, "error": f"Erreur d'exécution: {e}"}

    finally:
        if run_id:
            process_registry.unregister(run_id)

    # Process tué depuis /stop pendant communicate() : returncode négatif
    # (signal reçu) plutôt qu'une exception -> on le rapporte comme un arrêt
    # volontaire, pas comme un échec de commande.
    if returncode is not None and returncode < 0:
        after = set(WORKSPACE.rglob("*"))
        new_files = after - before
        return {
            "ok": False,
            "error": "commande interrompue (stop demandé)",
            "stdout": stdout,
            "stderr": stderr,
            "code": returncode,
            "generated_images": [
                str(f.relative_to(WORKSPACE)) for f in new_files if f.suffix.lower() in IMAGE_SUFFIXES
            ],
        }

    after = set(WORKSPACE.rglob("*"))
    new_files = after - before

    generated_images = [
        str(f.relative_to(WORKSPACE))
        for f in new_files
        if f.suffix.lower() in IMAGE_SUFFIXES
    ]

    return {
        "ok": returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
        "code": returncode,
        "generated_images": generated_images,
    }
