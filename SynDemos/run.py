import subprocess
import time
import sys
from pathlib import Path

# =========================
# CONFIG
# =========================

# Dossier où vit le projet de l'agent autonome. D'après son README, on
# lance `uvicorn api.main:app --reload --port 8000` DEPUIS ce dossier.
# Adapte ce chemin si l'agent est ailleurs sur ton disque (ou mets-le à
# None pour ne pas le démarrer automatiquement depuis run.py).
AGENT_DIR = Path(__file__).parent / "agent"

BACKEND_CMD = [
    sys.executable, "-m", "uvicorn",
    "backend.api:app",
    "--host", "0.0.0.0",
    "--port", "9000",
    "--reload"
]

AGENT_CMD = [
    sys.executable, "-m", "uvicorn",
    "api.main:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--reload"
]

UI_CMD = [
    sys.executable, "-m", "http.server", "8080",
    "--directory", "ui"
]

# =========================
# START PROCESS
# =========================

def start_process(cmd, name, cwd=None):
    print(f"[START] {name}")
    return subprocess.Popen(cmd, cwd=cwd)


def main():

    processes = []

    # backend
    processes.append(start_process(BACKEND_CMD, "API"))

    # UI
    processes.append(start_process(UI_CMD, "UI"))

    # Agent (démarré uniquement si le dossier existe, pour ne pas planter
    # si l'agent n'est pas présent à cet endroit chez toi)
    if AGENT_DIR.exists():
        processes.append(start_process(AGENT_CMD, "AGENT", cwd=str(AGENT_DIR)))
    else:
        print(f"[SKIP] Agent introuvable dans {AGENT_DIR} -> lance-le toi-même "
              f"(uvicorn api.main:app --port 8000) ou corrige AGENT_DIR dans run.py")

    print("\n========================")
    print("SYSTEM RUNNING")
    print("API    -> http://localhost:9000")
    print("UI     -> http://localhost:8080")
    print("AGENT  -> http://localhost:8000")
    print("========================\n")

    try:
        while True:
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopping...")

        for p in processes:
            p.terminate()

        print("Stopped cleanly.")


if __name__ == "__main__":
    main()
