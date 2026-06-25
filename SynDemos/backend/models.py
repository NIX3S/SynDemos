import os
from dotenv import load_dotenv
import requests

load_dotenv()

MODEL_ENDPOINTS = {
    "coder": os.getenv("CODER_URL"),
    "docs": os.getenv("DOCS_URL"),
    "reasoning": os.getenv("REASONING_URL"),
}

import requests

import json
import requests

def ask_model_stream(model_name, messages):
    url = "http://localhost:11434/v1/chat/completions" #MODEL_ENDPOINTS[model_name]

    r = requests.post(
        url,
        json={
            "messages": messages,
            "stream": True,
            "model" : model_name
        },
        stream=True
    )
    print(r)
    for line in r.iter_lines(chunk_size=1):
        if not line:
            continue

        line = line.decode("utf-8").strip()

        # skip SSE prefix
        if line.startswith("data: "):
            line = line[6:].strip()

        if line == "[DONE]":
            break

        try:

            data = json.loads(line)
            print(data)
            token = (
                data
                .get("choices", [{}])[0]
                .get("delta", {})
                .get("content")
            )

            if token:
                yield token

        except Exception as e:
            # debug si besoin
            # print("parse error:", line, e)
            continue
        
def ask_model(model_name, messages):
    url = "http://localhost:11434/v1/chat/completions" #MODEL_ENDPOINTS[model_name]

    r = requests.post(url, json={
        "model": model_name,
        "messages": messages,
        "temperature": 0.2
    })

    return r.json()["choices"][0]["message"]["content"]