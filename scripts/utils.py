from pathlib import Path
import os

def get_project_root():
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "scripts":
            return parent.parent
    # Fallback: if not found, assume two levels up
    return current.parent.parent 