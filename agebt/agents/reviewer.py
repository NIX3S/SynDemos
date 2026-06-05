def review(code, path):
    if path.endswith(".py"):
        if "import" not in code:
            return {"ok": False, "reason": "missing imports"}

        if code.strip().startswith("{"):
            return {"ok": False, "reason": "json detected in file"}

    return {"ok": True}