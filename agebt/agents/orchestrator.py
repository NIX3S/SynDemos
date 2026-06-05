from core.llm import call_llm

PROMPT = """
You are an orchestrator.

You decide:
- plan
- tool
- final

Return ONLY JSON.

TOOLS:
- filesystem
- planner
"""

def decide(user_input, context):
    return call_llm("orchestrator", PROMPT, [
        {"role": "user", "content": user_input + "\n\n" + context}
    ])