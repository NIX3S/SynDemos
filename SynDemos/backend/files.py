"""
Extraction de texte depuis les fichiers joints à une conversation (.txt,
.py, .md, .json, .pdf, .docx, ...) pour les donner en contexte au modèle
ou à l'agent.

Les formats binaires (PDF, DOCX) ont des dépendances optionnelles : si
elles ne sont pas installées, on renvoie un message d'erreur clair au
lieu de planter le serveur :
    pip install pypdf python-docx
(et `pip install python-multipart` est nécessaire côté FastAPI pour
recevoir des fichiers en upload, indépendamment de ce module.)
"""

import io
import os

MAX_CHARS = 20000  # cap par fichier pour ne pas exploser le contexte du LLM

PLAIN_TEXT_EXTENSIONS = {
    ".txt", ".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".json", ".csv",
    ".html", ".css", ".yaml", ".yml", ".xml", ".sh", ".sql", ".java",
    ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".ini",
    ".toml", ".log", ".env",
}


def _truncate(text):
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + f"\n\n[... tronqué, fichier trop long ({len(text)} caractères) ...]"
    return text


def extract_text(filename, raw_bytes):
    """Renvoie (texte_extrait, erreur). Un seul des deux est non-None."""
    ext = os.path.splitext(filename)[1].lower()

    if ext in PLAIN_TEXT_EXTENSIONS or ext == "":
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("utf-8", errors="ignore")
        return _truncate(text), None

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, "Extraction PDF indisponible : installe 'pypdf' (pip install pypdf)."
        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages).strip()
            if not text:
                return None, "Aucun texte extractible dans ce PDF (probablement scanné/image)."
            return _truncate(text), None
        except Exception as e:
            return None, f"Erreur lors de la lecture du PDF : {e}"

    if ext == ".docx":
        try:
            import docx
        except ImportError:
            return None, "Extraction DOCX indisponible : installe 'python-docx' (pip install python-docx)."
        try:
            document = docx.Document(io.BytesIO(raw_bytes))
            text = "\n".join(p.text for p in document.paragraphs).strip()
            if not text:
                return None, "Aucun texte extractible dans ce document."
            return _truncate(text), None
        except Exception as e:
            return None, f"Erreur lors de la lecture du document : {e}"

    return None, f"Format '{ext}' non pris en charge pour l'instant."
