import json
import re

def parse_model_output(text):

    if isinstance(text, dict):
        return text

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            obj.setdefault("type", "invalid")
            return obj
    except:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group())
            obj.setdefault("type", "invalid")
            return obj
        except:
            pass

    return {
        "type": "invalid",
        "error": "parse_failed",
        "raw": text
    }