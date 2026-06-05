from tools.filesystem import (
    read_text_file,
    list_directory,
    search_files,
    apply_patch
)

def execute(step):
    action = step["action"]

    if action == "read":
        return read_text_file(step["path"])

    if action == "list":
        return list_directory(step.get("path", "."))

    if action == "search":
        return search_files(step.get("path", "."), step.get("pattern", "*.py"))

    if action == "edit":
        return apply_patch(step["path"], step["content"])

    return {"error": "unknown_action"}