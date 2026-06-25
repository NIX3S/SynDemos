"""
Gestion du contexte long terme (RAG léger) pour les threads de chat.

Problème résolu :
------------------
Avant, chaque appel au LLM renvoyait TOUT l'historique du thread
(`thread["messages"]` en entier). Sur un thread long, ça :
  - explose la taille du prompt envoyé au modèle (lent, coûteux, et
    certains modèles locaux ont un contexte limité) ;
  - n'apporte aucune pertinence particulière : les vieux messages sont
    envoyés qu'ils soient utiles ou non à la question posée.

Approche :
----------
On combine :
  1. Les N derniers messages tels quels (continuité immédiate de la
     conversation : ce qu'on vient de dire).
  2. Jusqu'à K messages plus anciens, choisis par similarité cosinus
     entre l'embedding du nouveau message et l'embedding de chaque
     ancien message indexé (pertinence sémantique).

Les embeddings sont calculés via l'endpoint Ollama `/api/embeddings`
(modèle configurable via la variable d'env `EMBED_MODEL`, par défaut
`nomic-embed-text` — à puller avec `ollama pull nomic-embed-text`).

Tout est "best effort" : si Ollama n'a pas le modèle d'embedding (ou
n'est pas joignable), on retombe simplement sur les N derniers messages
sans RAG, sans jamais faire planter le chat.

Stockage : un fichier JSON par thread dans data/embeddings/<thread_id>.json
(volontairement simple — pas de vraie base vectorielle, le volume par
thread reste petit).
"""

import os
import json
import math
from pathlib import Path
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

EMBED_DIR = Path("data/embeddings")
EMBED_DIR.mkdir(parents=True, exist_ok=True)


def _embed_path(thread_id):
    return EMBED_DIR / f"{thread_id}.json"


def get_embedding(text):
    """Renvoie le vecteur d'embedding d'un texte, ou None en cas d'échec
    (Ollama down, modèle d'embedding pas installé, etc.) — jamais bloquant."""
    if not text or not text.strip():
        return None
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=8,
        )
        r.raise_for_status()
        embedding = r.json().get("embedding")
        return embedding or None
    except Exception:
        return None


def _load_index(thread_id):
    path = _embed_path(thread_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(thread_id, index):
    try:
        _embed_path(thread_id).write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def delete_index(thread_id):
    path = _embed_path(thread_id)
    if path.exists():
        path.unlink()


def index_message(thread_id, role, content, msg_index):
    """Ajoute un message à l'index vectoriel du thread (best-effort)."""
    if not content or not content.strip():
        return

    vector = get_embedding(content)
    if vector is None:
        return

    index = _load_index(thread_id)
    index.append({
        "index": msg_index,
        "role": role,
        "content": content,
        "vector": vector,
    })
    _save_index(thread_id, index)


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def retrieve_relevant(thread_id, query, top_k=4, exclude_last_n=8):
    """Renvoie jusqu'à `top_k` anciens messages les plus pertinents pour
    `query`, en excluant les `exclude_last_n` derniers messages indexés
    (déjà couverts par le contexte "récent" -> pas de doublon)."""
    index = _load_index(thread_id)
    if not index:
        return []

    query_vec = get_embedding(query)
    if query_vec is None:
        return []

    cutoff = max(0, len(index) - exclude_last_n)
    candidates = index[:cutoff]
    if not candidates:
        return []

    scored = [
        (entry, _cosine(query_vec, entry["vector"]))
        for entry in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # seuil de similarité minimal pour éviter de remonter du bruit
    return [entry for entry, score in scored[:top_k] if score > 0.3]


def build_context(thread, new_user_message, max_recent=8, max_retrieved=4):
    """Construit la liste de messages [{role, content}, ...] à envoyer au
    LLM : N derniers messages + rappel RAG des messages anciens pertinents.

    Si le thread est court (<= max_recent messages), on renvoie tout
    l'historique tel quel : pas besoin de RAG, ça n'apporterait rien."""
    messages = thread["messages"]

    if len(messages) <= max_recent:
        return [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

    recent = messages[-max_recent:]
    relevant = retrieve_relevant(
        thread["thread_id"],
        new_user_message,
        top_k=max_retrieved,
        exclude_last_n=max_recent,
    )

    context = []
    if relevant:
        recall = "\n".join(
            f"- ({m['role']}) {m['content'][:300]}" for m in relevant
        )
        context.append({
            "role": "system",
            "content": (
                "Rappel d'éléments pertinents plus anciens de cette "
                "conversation (retrouvés par similarité sémantique), "
                "à utiliser si utile pour répondre :\n" + recall
            ),
        })

    context += [{"role": m["role"], "content": m["content"]} for m in recent]
    return context


def build_agent_prompt(thread, new_user_message, max_recent=6, max_retrieved=4):
    """Variante texte unique de build_context, pour l'agent autonome dont
    l'API `/ask` ne prend qu'un seul `prompt` (pas une liste de messages).
    On reformate le contexte sous forme de mini-transcript lisible."""
    context_messages = build_context(thread, new_user_message, max_recent, max_retrieved)

    lines = []
    for m in context_messages:
        if m["role"] == "system":
            lines.append(f"[Contexte de la conversation]\n{m['content']}")
        elif m["role"] == "user":
            lines.append(f"Utilisateur: {m['content']}")
        else:
            lines.append(f"Assistant: {m['content']}")

    return "\n\n".join(lines)
