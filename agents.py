import asyncio
import json
import re
import requests
import os
import glob
from pathlib import Path

# ==================================================
# CONFIG
# ==================================================

BASE_DIR = Path(".").resolve()
MODEL_URL = "http://localhost:11434/v1/chat/completions"

MODELS = {
    "orchestrator": "orchestrator:latest",
    "coder": "Coder:latest",
    "docs": "Docs:latest",
    "reasoning": "Reasoning:latest"
}

MAX_STEPS = 12
MAX_FILE_SIZE = 20000

workspace = {
    "files": {},
    "action_history": []
}

# ==================================================
# SAFE PATH
# ==================================================

def safe_path(path):
    try:
        if not path:
            return None

        p = Path(str(path))

        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (BASE_DIR / p).resolve()

        if not str(resolved).startswith(str(BASE_DIR)):
            return None

        return str(resolved)

    except:
        return None

# ==================================================
# TOOLS
# ==================================================

def list_directory(path="."):
    path = safe_path(path) or str(BASE_DIR)
    if not Path(path).is_dir():
        return {"error": "NOT_A_DIRECTORY"}
    return os.listdir(path)


def read_text_file(path):
    path = safe_path(path)
    if not path:
        return {"error": "INVALID_PATH"}

    p = Path(path)
    if not p.exists():
        return {"error": "FILE_NOT_FOUND"}

    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:MAX_FILE_SIZE]


def search_files(path=".", pattern="*.py"):
    path = safe_path(path) or str(BASE_DIR)
    return glob.glob(f"{path}/**/{pattern}", recursive=True)


def apply_patch(path, content):
    path = safe_path(path)
    if not path:
        return {"error": "INVALID_PATH"}

    # 🚨 HARD SAFETY CHECK
    if content.strip().startswith("{"):
        return {"error": "REFUSED_JSON_IN_FILE"}

    if '"type"' in content and '"answer"' in content:
        return {"error": "REFUSED_MODEL_RESPONSE_IN_FILE"}
    if is_python_file(path):
        if "def " not in content and "import" not in content:
            return {"error": "INVALID_PYTHON_CONTENT"}
    Path(path).write_text(content, encoding="utf-8")
    workspace["files"][path] = content

    return {"status": "written", "path": path}


def run_tool(tool, args):
    args = args or {}

    print(f"\n🔧 TOOL:", tool)
    print("ARGS:", args)

    if tool == "list_directory":
        return list_directory(args.get("path", "."))

    if tool == "read_text_file":
        return read_text_file(args.get("path"))

    if tool == "search_files":
        return search_files(args.get("path", "."), args.get("pattern", "*.py"))

    if tool == "apply_patch":
        return apply_patch(args.get("path"), args.get("content"))

    return {"error": "UNKNOWN_TOOL"}

# ==================================================
# LLM CALL
# ==================================================

def call_model(model, system_prompt, messages):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": False
    }

    r = requests.post(MODEL_URL, json=payload, timeout=300)
    data = r.json()

    return data["choices"][0]["message"]["content"]

# ==================================================
# PARSER (ROBUST)
# ==================================================

def parse(text):
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("type") in ["tool", "final", "delegate"]:
            return obj
    except:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group())
            if obj.get("type") in ["tool", "final", "delegate"]:
                return obj
        except:
            pass

    return {"type": "invalid"}

def is_python_file(path):
    return str(path).endswith(".py")

# ==================================================
# PROMPT V3 (IMPORTANT FIX)
# ==================================================

ORCHESTRATOR_PROMPT = """
# SYSTEM: FILESYSTEM ORCHESTRATOR AGENT

You control tools. You do NOT write normal text unless FINAL.

==================================================
## RULES
==================================================

- You MUST output ONLY valid JSON
- You can output ONLY ONE action at a time
- No explanations in tool outputs
- Always prefer tools over text
- Never hallucinate file content

==================================================
## TOOL FORMAT (STRICT)
==================================================

ALL tool calls must follow EXACT format:

{
  "type": "tool",
  "tool": "<tool_name>",
  "args": { ... }
}

==================================================
## AVAILABLE TOOLS
==================================================

### 1. read_text_file
Use BEFORE editing any file

{
  "type": "tool",
  "tool": "read_text_file",
  "args": { "path": "file.py" }
}

---

### 2. list_directory
Explore filesystem

{
  "type": "tool",
  "tool": "list_directory",
  "args": { "path": "." }
}

---

### 3. search_files
Find files

{
  "type": "tool",
  "tool": "search_files",
  "args": {
    "path": ".",
    "pattern": "*.py"
  }
}

---

### 4. apply_patch (MAIN WRITE TOOL)
Write FULL file content (never partial)

RULES:
- must contain full file
- overwrites file entirely
- must be valid Python if .py file

{
  "type": "tool",
  "tool": "apply_patch",
  "args": {
    "path": "file.py",
    "content": "FULL FILE CONTENT"
  }
}

==================================================
## WORKFLOW RULES
==================================================

1. If user mentions a file → ALWAYS read it first
2. Then modify using apply_patch (full rewrite)
3. Never use multiple tools in one step
4. If unsure → list_directory

==================================================
## FINAL OUTPUT
==================================================

Only when task is complete:

{
  "type": "final",
  "answer": "short natural language answer"
}

==================================================
## IMPORTANT BEHAVIOR RULE
==================================================

If you cannot comply:
→ return:

{
  "type": "tool",
  "tool": "list_directory",
  "args": { "path": "." }
}

CRITICAL RULE:
- apply_patch.content MUST be SOURCE CODE ONLY
- NEVER include JSON
- NEVER include explanations
- NEVER include natural language
- ONLY valid file content
"""

# ==================================================
# AGENT LOOP
# ==================================================

async def agent(user_input):

    messages = [{"role": "user", "content": user_input}]
    workspace["action_history"] = []

    for step in range(MAX_STEPS):

        print(f"\n🧠 STEP {step}")

        raw = call_model(
            MODELS["orchestrator"],
            ORCHESTRATOR_PROMPT,
            messages
        )

        print("\nRAW:", raw)

        action = parse(raw)

        print("\nACTION:", action)

        if action["type"] == "invalid":
            messages.append({
                "role": "user",
                "content": "INVALID JSON. Return ONLY tool or final JSON."
            })
            continue

        workspace["action_history"].append(action)

        # STOP LOOP PROTECTION
        if len(workspace["action_history"]) > 3:
            last3 = workspace["action_history"][-3:]
            if all(a.get("type") == "delegate" for a in last3):
                return "LOOP STOPPED"

        # FINAL
        if action["type"] == "final":
            return action["answer"]

        # TOOL
        if action["type"] == "tool":
            result = run_tool(action["tool"], action.get("args", {}))

            messages.append({
                "role": "assistant",
                "content": json.dumps(action)
            })

            messages.append({
                "role": "user",
                "content": f"TOOL_RESULT:\n{result}"
            })

    return "MAX_STEPS_REACHED"

# ==================================================
# MAIN
# ==================================================

if __name__ == "__main__":
    user_input = input(">>> ")
    result = asyncio.run(agent(user_input))
    print("\n========== FINAL ==========")
    print(result)