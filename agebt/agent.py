import asyncio
from config import MAX_STEPS, MODELS
from core.parser import parse_model_output
from core.llm import call_llm
from core.context import build_context
from tools.filesystem import read_text_file, write_text_file, apply_patch, list_directory
from agents.planner import create_plan

workspace_history = []

TOOLS = {
    "read_text_file": read_text_file,
    "write_text_file": write_text_file,
    "apply_patch": apply_patch,
    "list_directory": list_directory
}

async def run(user_input):

    context = build_context()

    plan = create_plan(user_input, context)

    messages = [{"role": "user", "content": user_input}]

    for step in range(MAX_STEPS):

        raw = call_llm(
            MODELS["planner"],
            "You are orchestrator",
            messages
        )

        action = parse_model_output(raw)
        action_type = action.get("type", "invalid")
        if action_type == "invalid":
            messages.append({
                "role": "user",
                "content": "Répond uniquement en JSON avec un champ type obligatoire."
            })
            continue
        workspace_history.append(action)
        
        if action_type == "final":
            return action["answer"]

        if action_type == "tool":
            tool = action["tool"]
            args = action.get("args", {})

            if tool in TOOLS:
                result = TOOLS[tool](**args)

                messages.append({
                    "role": "user",
                    "content": f"TOOL_RESULT: {result}"
                })

        if action_type == "delegate":
            return {"delegate": action["target"]}

    return "MAX_STEPS_REACHED"


if __name__ == "__main__":
    user_input = input(">>> ")
    result = asyncio.run(run(user_input))
    print(result)