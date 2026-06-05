import subprocess
import time
import sys

# =========================
# CONFIG
# =========================

BACKEND_CMD = [
    sys.executable, "-m", "uvicorn",
    "backend.api:app",
    "--host", "0.0.0.0",
    "--port", "9000",
    "--reload"
]

UI_CMD = [
    sys.executable, "-m", "http.server", "8080",
    "--directory", "ui"
]

# =========================
# START PROCESS
# =========================

def start_process(cmd, name):
    print(f"[START] {name}")
    return subprocess.Popen(cmd)


def main():

    processes = []

    # backend
    processes.append(start_process(BACKEND_CMD, "API"))

    # UI
    processes.append(start_process(UI_CMD, "UI"))

    print("\n========================")
    print("SYSTEM RUNNING")
    print("API   -> http://localhost:9000")
    print("UI    -> http://localhost:8080")
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