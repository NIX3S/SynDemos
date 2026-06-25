"""
tools/sandbox.py
=================
Tout ce qui touche à la sécurité d'exécution :
- normalisation/validation de chemins (anti path traversal)
- validation des commandes shell (whitelist + blacklist de motifs dangereux)

Isolé dans son propre module pour que la logique de sécurité soit
auditable en un seul endroit, et testable indépendamment des outils
qui l'utilisent.
"""

from __future__ import annotations

from pathlib import Path

from config import (
    WORKSPACE,
    ALLOWED_COMMANDS,
    COMMAND_ALIASES,
    FORBIDDEN_SUBSTRINGS,
)


class PathSecurityError(ValueError):
    pass


class CommandSecurityError(ValueError):
    pass


def normalize_path(path: str) -> Path:
    """
    Résout un chemin relatif/absolu fourni par le LLM en un chemin
    garanti à l'intérieur de WORKSPACE.

    Règles :
    - les séparateurs windows sont normalisés
    - un chemin déjà préfixé par le workspace est dé-préfixé puis
      re-résolu (idempotent, évite la duplication WORKSPACE/WORKSPACE/...)
    - toute tentative de sortir du workspace (../, lien symbolique
      pointant ailleurs, chemin absolu étranger) lève PathSecurityError
    """
    raw = str(path).strip().replace("\\", "/")
    workspace_str = str(WORKSPACE).replace("\\", "/")

    if raw.startswith(workspace_str):
        raw = raw[len(workspace_str):]

    raw = raw.lstrip("/")

    final_path = (WORKSPACE / raw).resolve()

    if WORKSPACE != final_path and WORKSPACE not in final_path.parents:
        raise PathSecurityError(f"Chemin hors du workspace interdit: {final_path}")

    return final_path


def validate_command(command: str) -> str:
    """
    Vérifie qu'une commande shell est autorisée.
    Retourne la commande potentiellement réécrite (alias résolu en tête),
    ou lève CommandSecurityError.
    """
    command = command.strip()

    if not command:
        raise CommandSecurityError("Commande vide")

    lowered = command.lower()
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad in lowered:
            raise CommandSecurityError(f"Motif interdit détecté: '{bad}'")

    head = command.split()[0]
    resolved = COMMAND_ALIASES.get(head, head)

    if resolved not in ALLOWED_COMMANDS:
        raise CommandSecurityError(f"Commande non autorisée: '{head}'")

    return command
