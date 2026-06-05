import asyncio
import json
import re
import requests
import os
from pathlib import Path
import glob
import sys

sys.stdout.reconfigure(encoding="utf-8")

MODEL = "coder"
BASE_DIR = Path(".").resolve()

MODEL_URL = "http://localhost:11434/v1/chat/completions"

# =========================
# SECURITY CONFIG (IMPORTANT)
# =========================
ALLOWED_TOOLS = {"list_directory", "read_text_file", "search_files"}

MAX_STEPS = 8


# =========================
# SYSTEM PROMPT (STRICT)
# =========================
SYSTEM_PROMPT = f"""
Tu es un agent filesystem.

Tu travailles uniquement dans:
{BASE_DIR}

RÈGLES ABSOLUES:
- Tu DOIS utiliser des tools pour toute info fichier
- Tu ne dois jamais inventer le contenu des fichiers
- Tu dois explorer avant de répondre
- Tu ne peux répondre final QUE si les fichiers nécessaires ont été lus

TOOLS DISPONIBLES:
- list_directory(path)
- read_text_file(path)
- search_files(path, pattern)

FORMAT UNIQUE:
{{
  "type": "tool" | "final",
  "tool": "...",
  "args": {{}},
  "answer": "..."
}}
"""


# =========================
# PATH SAFETY
# =========================
def normalize_path(p):
    if not p:
        return "."

    p = str(p)

    # reject absolute hallucinations
    if p.startswith("/mnt") or p.startswith("/path"):
        return "."

    return p


def safe_path(path):
    try:
        if not path:
            return None

        path = str(path)

        if "path/to" in path:
            return None

        p = Path(path)

        # ABSOLUTE PATH → must exist
        if p.is_absolute():
            return str(p) if p.exists() else None

        full = (BASE_DIR / p).resolve()

        if not str(full).startswith(str(BASE_DIR)):
            return None

        return str(full) if full.exists() else None

    except:
        return None


# =========================
# TOOLS
# =========================
def list_directory(path="."):
    try:
        path = safe_path(path) or str(BASE_DIR)

        if not Path(path).is_dir():
            return {"error": "NOT_A_DIRECTORY"}

        return os.listdir(path)

    except Exception as e:
        return {"error": str(e)}


def read_text_file(path):
    try:
        path = safe_path(path)

        if not path:
            return {"error": "FILE_NOT_FOUND"}

        p = Path(path)

        if not p.is_file():
            return {"error": "NOT_A_FILE"}

        return p.read_text(encoding="utf-8", errors="ignore")

    except Exception as e:
        return {"error": str(e)}


def search_files(path=".", pattern="*.py"):
    try:
        path = safe_path(path) or str(BASE_DIR)

        if not Path(path).is_dir():
            return {"error": "NOT_A_DIRECTORY"}

        return glob.glob(f"{path}/**/{pattern}", recursive=True)

    except Exception as e:
        return {"error": str(e)}


# =========================
# TOOL EXECUTION SAFE
# =========================
def run_tool(tool, args):
    try:
        print(f"\n🔧 TOOL: {tool}")
        print("ARGS:", args)

        if tool not in ALLOWED_TOOLS:
            return {"error": "TOOL_NOT_ALLOWED"}

        args = args or {}

        if tool == "list_directory":
            return list_directory(args.get("path", "."))

        if tool == "read_text_file":
            return read_text_file(args.get("path"))

        if tool == "search_files":
            return search_files(
                args.get("path", "."),
                args.get("pattern", "*.py")
            )

        return {"error": "UNKNOWN_TOOL"}

    except Exception as e:
        return {"error": str(e)}


# =========================
# LLM CALL
# =========================
def call_llm(messages):
    r = requests.post(
        MODEL_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "stream": True
        },
        stream=True
    )

    out = ""

    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue

        if line.startswith("data: "):
            line = line[6:].strip()

        if line == "[DONE]":
            break

        try:
            data = json.loads(line)
            token = data.get("choices", [{}])[0].get("delta", {}).get("content")

            if token:
                print(token, end="", flush=True)
                out += token

        except:
            continue

    print()
    return out


# =========================
# PARSER (ROBUST)
# =========================
def parse(text):
    if not text or not isinstance(text, str):
        return {"type": "final", "answer": str(text)}

    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "type" in obj:
            return obj
    except:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict) and "type" in obj:
                return obj
        except:
            pass

    return {"type": "final", "answer": text}


# =========================
# VALIDATION (CRITICAL SAFETY)
# =========================
def validate_action(action):
    if not isinstance(action, dict):
        return {"type": "final", "answer": str(action)}

    if action.get("type") == "tool":
        tool = action.get("tool")

        if tool not in ALLOWED_TOOLS:
            return {
                "type": "tool",
                "tool": "list_directory",
                "args": {"path": "."}
            }

        args = action.get("args") or {}

        # FORCE VALID PATHS
        if "path" in args and not args["path"]:
            args["path"] = "."

        action["args"] = args

    return action


def is_final(action):
    return (
        isinstance(action, dict)
        and action.get("type") == "final"
        and action.get("answer") is not None
    )


# =========================
# DEBUG
# =========================
def debug(title, data):
    print(f"\n========== {title} ==========")
    print(data)
    print("=" * 50 + "\n")


# =========================
# AGENT V11 (STABLE LOOP)
# =========================
async def agent(user_input):

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ]

    for step in range(MAX_STEPS):

        print(f"\n🧠 STEP {step}")

        raw = call_llm(messages)
        debug("RAW LLM OUTPUT", raw)

        action = parse(raw)
        action = validate_action(action)

        debug("ACTION", action)

        if is_final(action):
            return action["answer"]

        if action.get("type") != "tool":
            return {"error": "invalid_action"}

        tool = action["tool"]
        args = action.get("args", {})

        result = run_tool(tool, args)

        debug("TOOL RESULT", result)

        messages.append({
            "role": "assistant",
            "content": json.dumps(action)
        })

        messages.append({
            "role": "user",
            "content": f"Tool result:\n{result}"
        })

    return "Max steps reached"


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    user_input = input(">>> ")
    result = asyncio.run(agent(user_input))

    print("\n========== FINAL ==========")
    print(result)