"""
Client pour parler à l'agent autonome (projet séparé, non modifié ici),
exposé en SSE sur `POST /ask` (cf. son README).

Ce module fait deux choses :
  1. ask_agent_stream()  : consomme le flux SSE et yield chaque événement
     JSON déjà parsé ({"type": ..., "data": ...}).
  2. summarize_event()   : transforme un événement brut en une ligne de
     texte lisible, pour le panneau "travail de l'agent" affiché puis
     replié dans l'UI.
"""

import os
import json
import requests

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")


def ask_agent_stream(prompt, model=None, timeout=900):
    """Appelle POST {AGENT_URL}/ask et yield chaque événement JSON reçu.

    Robuste à deux formats de ligne possibles :
      - JSON brut par ligne : {"type": "...", "data": {...}}
      - SSE classique avec préfixe "data: " (au cas où l'agent évolue
        vers ce format un jour).
    """
    payload = {"prompt": prompt}
    if model:
        payload["model"] = model

    with requests.post(
        f"{AGENT_URL}/ask",
        json=payload,
        stream=True,
        timeout=timeout,
    ) as r:
        r.raise_for_status()
        for raw_line in r.iter_lines(decode_unicode=True):
            if not raw_line:
                continue

            line = raw_line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()

            if not line or line == "[DONE]":
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            yield event


def summarize_event(evt):
    """Transforme un événement brut de l'agent en une ligne lisible pour
    le panneau repliable 'travail de l'agent' côté UI. Les clés exactes
    de `data` ne sont pas garanties par le README -> on reste défensif
    avec des `.get(...)` et plusieurs noms de clés possibles."""
    etype = evt.get("type", "?")
    data = evt.get("data", {}) or {}
    data_dict = data if isinstance(data, dict) else {}

    if etype == "start":
        return f"🚀 Démarrage du run (id: {evt.get('run_id', '?')})"

    if etype == "plan":
        cat = data_dict.get("task_category")
        model_used = data_dict.get("model_used")
        suffix = f" — catégorie: {cat}" if cat else ""
        suffix += f" — modèle: {model_used}" if model_used else ""
        return f"🗒️ Plan généré{suffix}"

    if etype == "todo_update":

        if isinstance(data, list):
            todos = data
        else:
            todos = data_dict.get("todos") or []

        if not todos:
            return "✅ Mise à jour de la liste de tâches"

        lines = []

        for t in todos:
            title = (
                t.get("title")
                or t.get("label")
                or t.get("text")
                or ""
            )

            lines.append(
                f"   [{t.get('status', '?')}] {title}"
            )

        return "✅ Todos:\n" + "\n".join(lines)

    if etype == "exec":
        content = data_dict.get("content", "").strip()

        if content:
            return f"⚙️ {content[:120]}"

        tools = data_dict.get("tools", [])

        if tools:
            return f"⚙️ Exécution de {len(tools)} outil(s)"

        return "⚙️ Exécution"
    

    if etype == "tool_result":
        if isinstance(data, list):
            return f"🔧 Outils exécutés: {', '.join(data)}"

        tool = data_dict.get("tool", "?")
        ok = data_dict.get("ok", data_dict.get("success"))

        mark = "✔" if ok else ("✘" if ok is False else "•")

        detail = (
            data_dict.get("path")
            or data_dict.get("command")
            or ""
        )

        return f"🔧 {tool} {mark} {detail}".strip()

    if etype == "checkpoint":
        path = (
            data_dict.get("rel_path")
            or data_dict.get("path")
            or data_dict.get("file")
            or "?"
        )

        return f"💾 Checkpoint sur {path}"
    if etype == "verify":
        ok = data_dict.get("ok", data_dict.get("success"))
        return f"🔍 Vérification: {'OK' if ok else ('échec' if ok is False else 'en cours...')}"

    if etype == "error":
        return f"❌ Erreur: {data_dict.get('message') or data}"
    if etype == "final":
        return "🏁 Exécution terminée"

    return f"• {etype}"
