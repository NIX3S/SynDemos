"""
api/main.py
============
Point d'entrée FastAPI.

Lancer :
    uvicorn api.main:app --reload --port 8000

Important : `import tools` ici déclenche l'enregistrement de tous les
outils (write_file, edit_file, read_file, list_dir, shell, read_pdf,
inspect_pdf, web_search, web_fetch) via les décorateurs @tool. Sans cet
import, TOOL_REGISTRY serait vide et le LLM n'aurait aucun outil
disponible.

Au démarrage, la liste des outils réellement enregistrés est loguée —
si un outil attendu manque (ex: web_search absent), c'est visible
immédiatement dans les logs serveur plutôt que découvert au milieu d'un
run, sans qu'aucune lib manquante (requests/bs4/pypdf) ne fasse planter
le démarrage du serveur entier (chaque outil a un import lazy de ses
dépendances optionnelles, géré dans son propre module).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

import tools  # noqa: F401  (enregistrement des outils — ne pas retirer)
from api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("agent.startup")
logger.info("Outils enregistrés au démarrage: %s", sorted(tools.TOOL_REGISTRY.keys()))

app = FastAPI(title="Autonomous Agent API", version="2.0.0")
app.include_router(router)
