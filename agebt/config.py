from pathlib import Path

BASE_DIR = Path(".").resolve()

MODEL_URL = "http://localhost:11434/v1/chat/completions"

MODELS = {
    "planner": "orchestrator:latest",
    "coder": "coder:latest",
    "reviewer": "reasoning:latest"
}

MAX_STEPS = 12
MEMORY_FILE = "memory/threads.json"
WORKSPACE_FILE = "memory/workspace.json"