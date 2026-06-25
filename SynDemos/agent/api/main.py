"""
api/main.py
============
Point d'entrée FastAPI.

Lancer :
    uvicorn api.main:app --reload --port 8000

Important : `import tools` ici déclenche l'enregistrement de tous les
outils (write_file, edit_file, read_file, list_dir, shell) via les
décorateurs @tool. Sans cet import, TOOL_REGISTRY serait vide et le
LLM n'aurait aucun outil disponible.
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

app = FastAPI(title="Autonomous Agent API", version="2.0.0")
app.include_router(router)
