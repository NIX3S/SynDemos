import requests
from config import MODEL_URL

def call_llm(model, system, messages):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "stream": False
    }

    r = requests.post(MODEL_URL, json=payload, timeout=300)

    try:
        data = r.json()
    except Exception:
        return {"error": "INVALID_JSON", "raw": r.text}

    # ✅ FIX CRITIQUE
    if "choices" not in data:
        return {
            "error": "NO_CHOICES",
            "raw": data
        }

    return data["choices"][0]["message"]["content"]