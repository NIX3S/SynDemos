"""
tools/web_tools.py
====================
Recherche web et lecture de pages, sans API tierce payante : requête
HTTP directe + parsing HTML via BeautifulSoup.

Moteur de recherche : DuckDuckGo HTML (html.duckduckgo.com), choisi
plutôt que Google directement parce que :
- pas de JavaScript nécessaire pour afficher les résultats (contrairement
  à google.com qui rend son contenu côté client)
- pas de blocage anti-bot agressif pour un usage raisonnable
- pas de clé API, pas de compte, pas de quota payant à gérer

Deux outils complémentaires, pensés pour que le LLM puisse JUGER la
qualité de ses propres résultats et décider lui-même de relancer une
recherche avec des termes différents si besoin (ex: "tarte citron" ->
résultats jugés trop vagues -> "tarte citron meringuée") :

- web_search(query) : retourne titre + extrait (snippet) + URL pour
  chaque résultat. Le snippet est la donnée clé : c'est ce qui permet
  au LLM d'évaluer la pertinence SANS avoir à ouvrir chaque page.
- web_fetch(url) : va lire le contenu texte complet d'une page précise,
  pour approfondir un résultat jugé prometteur par web_search.

Rien de cet outil n'est activé par défaut sans confirmation implicite :
contrairement aux providers LLM externes (voir llm/registry.py), faire
une requête HTTP de lecture (GET) vers un moteur de recherche public ne
partage pas de clé ni de données sensibles, donc pas de flag de sécurité
supplémentaire ici — mais l'outil n'est utilisable que si `requests` et
`bs4` sont installés (import lazy, erreur claire sinon).
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from config import (
    WEB_REQUEST_TIMEOUT,
    WEB_MAX_RESULTS_DEFAULT,
    WEB_MAX_RESULTS_HARD_CAP,
    WEB_MAX_FETCH_CHARS,
)
from tools.registry import tool

logger = logging.getLogger("agent.tools.web")

SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = WEB_REQUEST_TIMEOUT
MAX_RESULTS_DEFAULT = WEB_MAX_RESULTS_DEFAULT
MAX_RESULTS_HARD_CAP = WEB_MAX_RESULTS_HARD_CAP
MAX_FETCH_CHARS = WEB_MAX_FETCH_CHARS


def _load_http_libs():
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError(
            "requests et beautifulsoup4 ne sont pas installés. "
            "Ajoute 'requests' et 'beautifulsoup4' à requirements.txt et réinstalle."
        ) from e
    return requests, BeautifulSoup


def _is_safe_url(url: str) -> bool:
    """
    Garde-fou minimal : on ne récupère que du http(s), jamais file://,
    ftp://, ni une IP locale/privée évidente (anti SSRF basique — l'agent
    ne doit pas pouvoir se servir de web_fetch pour sonder le réseau
    interne de la machine qui l'héberge).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = (parsed.hostname or "").lower()
    if not host:
        return False

    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host in blocked_hosts:
        return False

    if host.startswith("169.254.") or host.startswith("10.") or host.startswith("192.168."):
        return False
    if host.startswith("172."):
        try:
            second_octet = int(host.split(".")[1])
            if 16 <= second_octet <= 31:
                return False
        except (IndexError, ValueError):
            pass

    return True


@tool(
    "web_search",
    {
        "description": (
            "Rechercher sur le web (via DuckDuckGo) et obtenir une liste de "
            "résultats avec titre, extrait (snippet) et URL. Utilise le "
            "snippet pour juger si les résultats répondent à la question — "
            "si non, relance une recherche avec des termes plus précis ou "
            "différents plutôt que de te contenter de résultats faibles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termes de recherche"},
                "max_results": {
                    "type": "integer",
                    "description": f"Nombre de résultats souhaités (1-{MAX_RESULTS_HARD_CAP}, défaut {MAX_RESULTS_DEFAULT})",
                },
            },
            "required": ["query"],
        },
    },
)
def web_search(query: str, max_results: int = MAX_RESULTS_DEFAULT) -> dict[str, Any]:
    try:
        requests, BeautifulSoup = _load_http_libs()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    query = query.strip()
    if not query:
        return {"ok": False, "error": "query vide"}

    max_results = max(1, min(max_results, MAX_RESULTS_HARD_CAP))

    try:
        resp = requests.post(
            SEARCH_URL,
            data={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"timeout après {REQUEST_TIMEOUT}s en contactant le moteur de recherche"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"échec de la requête de recherche: {e}"}

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for block in soup.select(".result")[: max_results * 2]:  # marge avant filtrage
        title_el = block.select_one(".result__title a") or block.select_one("a.result__a")
        snippet_el = block.select_one(".result__snippet")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        snippet = snippet_el.get_text(separator=" ", strip=True) if snippet_el else ""
        snippet = " ".join(snippet.split())  # normalise les espaces multiples résiduels

        if not title or not url:
            continue

        results.append({"title": title, "url": url, "snippet": snippet})

        if len(results) >= max_results:
            break

    return {
        "ok": True,
        "query": query,
        "count": len(results),
        "results": results,
        "note": (
            "Aucun résultat — reformule la requête (termes plus spécifiques "
            "ou différents) avant de conclure qu'il n'y a rien."
            if not results
            else "Si ces résultats ne répondent pas assez précisément à la "
            "question, relance web_search avec une requête plus ciblée."
        ),
    }


@tool(
    "web_fetch",
    {
        "description": (
            "Récupérer le contenu texte d'une page web précise (par son URL), "
            "typiquement une URL retournée par web_search jugée prometteuse. "
            "Le contenu est tronqué s'il est trop long."
        ),
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
)
def web_fetch(url: str) -> dict[str, Any]:
    try:
        requests, BeautifulSoup = _load_http_libs()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    if not _is_safe_url(url):
        return {"ok": False, "error": "URL refusée (schéma non http(s) ou cible réseau interne/locale)"}

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"timeout après {REQUEST_TIMEOUT}s"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"échec de la requête: {e}"}

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        return {"ok": False, "error": f"type de contenu non supporté: {content_type or 'inconnu'}"}

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    truncated = len(text) > MAX_FETCH_CHARS
    if truncated:
        text = text[:MAX_FETCH_CHARS]

    title = soup.title.get_text(strip=True) if soup.title else ""

    return {
        "ok": True,
        "url": url,
        "title": title,
        "truncated": truncated,
        "content": text,
    }
