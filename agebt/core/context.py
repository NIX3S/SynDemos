from tools.filesystem import workspace

def build_context():
    return "\n\n".join(
        f"{k}\n{v}" for k, v in workspace.items()
    )