"""
tools/process_registry.py
===========================
Registre des process shell actifs, indexé par run_id.

Permet à l'endpoint /stop/{run_id} de tuer une commande shell en cours
d'exécution (ex: un script qui boucle) sans attendre son timeout. Sans
ce registre, /stop ne prenait effet qu'entre deux appels d'outils,
jamais PENDANT un appel shell qui peut durer jusqu'à AGENT_SHELL_TIMEOUT
(120s) ou AGENT_SHELL_PIP_TIMEOUT (300s).

Certaines commandes (matchant PROTECTED_COMMAND_PREFIXES) sont marquées
"protégées" : un premier appel à /stop sur un process protégé ne le tue
pas — il faut un second appel explicite avec force=True pour vraiment
l'interrompre. Deux familles de commandes sont protégées, pour des
raisons légèrement différentes :

- pip / pip3 : presque toujours légitimement longs (téléchargement,
  compilation de wheels). Quasiment jamais une erreur de l'agent.
- python / python3 : un script peut être un calcul long et légitime
  (entraînement ML avec scikit-learn/torch, traitement de données
  volumineux) OU une vraie boucle infinie bugguée que l'agent a écrite
  par erreur. On ne peut pas distinguer les deux juste sur la commande
  — donc on ne tue jamais automatiquement (pas de timeout interne), mais
  on ne retire pas non plus le contrôle humain : un /stop reste toujours
  possible avec force=True si quelqu'un juge que ça tourne trop longtemps.
  C'est la même logique qu'un agent qui ne s'auto-interrompt jamais en
  plein calcul, mais qui reste interruptible sur demande explicite.

Thread-safe au sens basique : un seul process actif par run_id à la fois
(l'agent exécute ses tool_calls séquentiellement, jamais en parallèle
sur un même run), donc un simple dict protégé par un lock suffit.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass

# Préfixes de commande considérés "longs et légitimes" : un premier
# /stop sur ces commandes ne tue pas, il prévient seulement.
PROTECTED_COMMAND_PREFIXES: tuple[str, ...] = (
    "pip install", "pip3 install", "pip", "pip3",
    "python ", "python3 ",
)


@dataclass
class ActiveProcess:
    proc: subprocess.Popen
    command: str
    started_at: float

    @property
    def is_protected(self) -> bool:
        return self.command.strip().startswith(PROTECTED_COMMAND_PREFIXES)


_lock = threading.Lock()
_active: dict[str, ActiveProcess] = {}


def register(run_id: str, proc: subprocess.Popen, command: str) -> None:
    with _lock:
        _active[run_id] = ActiveProcess(proc=proc, command=command, started_at=time.time())


def unregister(run_id: str) -> None:
    with _lock:
        _active.pop(run_id, None)


def get_active(run_id: str) -> ActiveProcess | None:
    with _lock:
        return _active.get(run_id)


def kill(run_id: str, force: bool = False) -> dict:
    """
    Tue le process shell actif pour ce run_id, si il y en a un — et tout
    son groupe de processus (pas seulement son PID), car il a été lancé
    avec start_new_session=True dans shell_tool.py.

    Retourne un statut structuré :
      {"status": "no_process"}                          rien à tuer
      {"status": "confirmation_required", "command": .} process protégé,
                                                          pas tué, attend force=True
      {"status": "killed", "command": ...}               vraiment tué
    """
    active = get_active(run_id)

    if active is None:
        return {"status": "no_process"}

    if active.is_protected and not force:
        return {
            "status": "confirmation_required",
            "command": active.command,
            "running_for_seconds": round(time.time() - active.started_at, 1),
        }

    try:
        os.killpg(os.getpgid(active.proc.pid), signal.SIGKILL)
        return {"status": "killed", "command": active.command}
    except ProcessLookupError:
        return {"status": "no_process"}
