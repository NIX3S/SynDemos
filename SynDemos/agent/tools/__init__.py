"""
tools/__init__.py
==================
Importer ce package déclenche l'enregistrement de tous les outils
(via le décorateur @tool dans fs_tools.py et shell_tool.py).

Le reste du code n'a besoin que de :
    from tools.registry import get_tool, all_tool_schemas
"""

from tools import fs_tools  # noqa: F401  (enregistre write_file, read_file, edit_file, list_dir)
from tools import shell_tool  # noqa: F401  (enregistre shell)
from tools import pdf_tools  # noqa: F401  (enregistre read_pdf, inspect_pdf)
from tools import web_tools  # noqa: F401  (enregistre web_search, web_fetch)
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS  # noqa: F401
