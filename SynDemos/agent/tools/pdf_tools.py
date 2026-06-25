"""
tools/pdf_tools.py
====================
Lecture de fichiers PDF du workspace : extraction de texte, page par page
ou plage de pages, avec un inventaire (nombre de pages, présence de texte)
pour que l'agent sache s'il a affaire à un PDF texte ou à un scan avant
de se lancer dans une extraction qui ne renverra rien.

Choix : pypdf (pure Python, déjà listé dans requirements.txt) plutôt que
poppler-utils (pdftotext) pour ne pas dépendre d'un binaire système —
plus simple à déployer (Docker, etc.). Pour des PDF scannés/sans couche
texte, le résultat sera vide ; ce n'est pas un bug, c'est signalé
explicitement dans le retour (has_text_layer: false) plutôt que de
renvoyer une chaîne vide sans explication.

Import de pypdf fait à l'intérieur des fonctions (lazy) : si la lib
n'est pas installée, l'outil retourne une erreur claire au lieu de faire
planter l'enregistrement de TOUS les outils au démarrage du serveur.
"""

from __future__ import annotations

from typing import Any

from tools.registry import tool
from tools.sandbox import normalize_path, PathSecurityError

MAX_CHARS_PER_RESULT = 50_000  # garde-fou : éviter de saturer le contexte du LLM avec un PDF de 800 pages


def _load_reader(p):
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "pypdf n'est pas installé. Ajoute 'pypdf' à requirements.txt et réinstalle."
        ) from e

    return PdfReader(str(p))


@tool(
    "read_pdf",
    {
        "description": (
            "Extraire le texte d'un PDF du workspace. Retourne le texte des "
            "pages demandées (toutes par défaut), tronqué si trop long. "
            "Utiliser inspect_pdf d'abord sur un gros document pour connaître "
            "le nombre de pages et cibler une plage utile."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin relatif au workspace"},
                "start_page": {
                    "type": "integer",
                    "description": "Première page à extraire (1-indexée). Défaut: 1.",
                },
                "end_page": {
                    "type": "integer",
                    "description": "Dernière page à extraire (incluse). Défaut: dernière page.",
                },
            },
            "required": ["path"],
        },
    },
)
def read_pdf(path: str, start_page: int = 1, end_page: int | None = None) -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    if not p.exists():
        return {"ok": False, "error": "Fichier introuvable"}

    try:
        reader = _load_reader(p)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"PDF illisible ou corrompu: {e}"}

    total_pages = len(reader.pages)

    if total_pages == 0:
        return {"ok": False, "error": "PDF sans aucune page"}

    start = max(1, start_page)
    end = min(total_pages, end_page if end_page is not None else total_pages)

    if start > end:
        return {"ok": False, "error": f"start_page ({start}) > end_page ({end})"}

    parts: list[str] = []
    for i in range(start - 1, end):
        try:
            page_text = reader.pages[i].extract_text() or ""
        except Exception as e:
            page_text = f"[erreur extraction page {i + 1}: {e}]"
        parts.append(f"--- page {i + 1} ---\n{page_text}")

    full_text = "\n\n".join(parts)
    truncated = len(full_text) > MAX_CHARS_PER_RESULT

    if truncated:
        full_text = full_text[:MAX_CHARS_PER_RESULT]

    return {
        "ok": True,
        "total_pages": total_pages,
        "extracted_pages": [start, end],
        "has_text_layer": bool(full_text.strip()),
        "truncated": truncated,
        "content": full_text,
    }


@tool(
    "inspect_pdf",
    {
        "description": (
            "Inspecter un PDF sans extraire son texte : nombre de pages, "
            "métadonnées, et si une couche de texte existe (sinon c'est "
            "probablement un scan — read_pdf renverra du vide). À utiliser "
            "avant read_pdf sur un document volumineux ou inconnu."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
)
def inspect_pdf(path: str) -> dict[str, Any]:
    try:
        p = normalize_path(path)
    except PathSecurityError as e:
        return {"ok": False, "error": str(e)}

    if not p.exists():
        return {"ok": False, "error": "Fichier introuvable"}

    try:
        reader = _load_reader(p)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"PDF illisible ou corrompu: {e}"}

    total_pages = len(reader.pages)

    # sonde la 1ère page seulement (rapide) pour estimer si une couche de texte existe
    sample_text = ""
    if total_pages > 0:
        try:
            sample_text = reader.pages[0].extract_text() or ""
        except Exception:
            sample_text = ""

    meta = reader.metadata or {}

    return {
        "ok": True,
        "total_pages": total_pages,
        "likely_has_text_layer": bool(sample_text.strip()),
        "title": getattr(meta, "title", None),
        "author": getattr(meta, "author", None),
        "encrypted": reader.is_encrypted,
    }
