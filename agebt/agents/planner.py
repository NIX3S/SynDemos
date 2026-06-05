from core.llm import call_llm

PLANNER_PROMPT = """
You are a planner.

Break task into steps.

Return ONLY JSON:

{
  "steps": [
    {"action": "read", "path": "..."},
    {"action": "edit", "path": "...", "content": "..."}
  ]
}
"""

def create_plan(task, context):
    return call_llm("planner", PLANNER_PROMPT, [
        {"role": "user", "content": f"{task}\n\n{context}"}
    ])