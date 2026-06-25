"""
tools/fs_tools.py
==================
Outils de manipulation de fichiers, tous bornés au WORKSPACE via
tools.sandbox.normalize_path.

Bugs corrigés par rapport à l'ancien tools.py :
- write_file : `diff` était une variable locale jamais initialisée quand
  le fichier était nouveau (old_content is None) -> UnboundLocalError au
  retour. Ici `diff` est TOUJOURS défini avant le `return`.
- write_file : un `Path(path).name if path.endswith(".py")` tronquait
  silencieusement les sous-dossiers pour tout fichier .py (donc
  `src/app.py` devenait `app.py` à la racine). Supprimé : on fait
  confiance à normalize_path pour la sécurité, pas de logique ad-hoc
  qui mutile les chemins.

Ajout (style Claude Code) :
- edit_file : remplace une chaîne unique dans un fichier, comme un
  str_replace. Plus sûr qu'une réécriture complète pour des petites
  corrections, et ça donne un diff naturellement petit et lisible.
- list_dir : permet au LLM d'explorer l'arborescence du workspace
  sans deviner les noms de fichiers.
"""

from __future__ import annotations

from config import WORKSPACE
from difflib import unified_diff
from pathlib import Path
from typing import Any

from tools.registry import tool
from tools.sandbox import normalize_path, PathSecurityError


def _snapshot(path: Path) -> str | None:
    if path.exists() and path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _diff(before: str | None, after: str) -> str:
    return "\n".join(
        unified_diff(
            (before or "").splitlines(),
            after.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


@tool(
    "write_file",
    {
        "description": "Créer un fichier ou écraser entièrement son contenu.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin relatif au workspace"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
)
def write_file(path: str, content: str) -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    p.parent.mkdir(parents=True, exist_ok=True)

    before = _snapshot(p)
    p.write_text(content, encoding="utf-8")
    after = p.read_text(encoding="utf-8")

    return {
        "ok": True,
        "rel_path": str(p.relative_to(WORKSPACE)),
        "created": before is None,
        "diff": _diff(before, after),
        "previous_content": before,
    }


@tool(
    "edit_file",
    {
        "description": (
            "Remplacer une chaîne EXACTE et UNIQUE dans un fichier existant. "
            "Préférable à write_file pour une petite correction : si "
            "old_str n'est pas trouvé exactement une fois, l'outil échoue "
            "proprement au lieu de deviner."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
)
def edit_file(path: str, old_str: str, new_str: str) -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    if not p.exists():
        return {"ok": False, "error": f"Fichier introuvable: {path}"}

    before = p.read_text(encoding="utf-8")
    count = before.count(old_str)

    if count == 0:
        return {"ok": False, "error": "old_str introuvable dans le fichier"}
    if count > 1:
        return {
            "ok": False,
            "error": f"old_str apparaît {count} fois — doit être unique",
        }

    after = before.replace(old_str, new_str, 1)
    p.write_text(after, encoding="utf-8")

    return {
        "ok": True,
        "rel_path": str(p.relative_to(WORKSPACE)),
        "diff": _diff(before, after),
        "previous_content": before,
    }


@tool(
    "read_file",
    {
        "description": "Lire le contenu d'un fichier du workspace.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
)
def read_file(path: str) -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    if not p.exists():
        return {"ok": False, "error": "Fichier introuvable"}
    if not p.is_file():
        return {"ok": False, "error": "Ce n'est pas un fichier"}

    try:
        return {"ok": True, "content": p.read_text(encoding="utf-8")}
    except UnicodeDecodeError:
        return {"ok": False, "error": "Fichier binaire, lecture impossible"}


@tool(
    "list_dir",
    {
        "description": "Lister les fichiers et dossiers à un chemin du workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Chemin relatif, '.' pour la racine du workspace",
                }
            },
            "required": ["path"],
        },
    },
)
def list_dir(path: str = ".") -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    if not p.exists():
        return {"ok": False, "error": "Chemin introuvable"}
    if not p.is_dir():
        return {"ok": False, "error": "Ce n'est pas un dossier"}

    entries = sorted(
        f"{e.name}/" if e.is_dir() else e.name for e in p.iterdir()
    )
    return {"ok": True, "entries": entries}
