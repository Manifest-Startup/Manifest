import os
import subprocess
import shutil
import sys
import argparse
from pathlib import Path
from utils import get_project_root

def safe_run(cmd_list, description=""):
    try:
        print(f"🔧 {description}...")
        subprocess.run(cmd_list, check=True)
    except FileNotFoundError:
        print(f"⚠️  Command not found: {cmd_list[0]}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running command: {' '.join(cmd_list)}")
        print(e)

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="Preview deletions without executing them")
parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
args = parser.parse_args()

PROJECT_ROOT = get_project_root()

# Detect the currently active virtual environment path
active_venv_path = Path(sys.executable).resolve().parent.parent

# Run Docker system prune if Docker is available
if shutil.which("docker"):
    safe_run(["docker", "system", "prune", "-af", "--volumes"], "Running Docker system prune")
else:
    print("⚠️  Docker not found. Skipping Docker cleanup.")

raw_paths_to_delete = [
    ".venv", "env",
    "backend/.venv", "backend/env",
    "frontend/node_modules", "frontend/package-lock.json", "frontend/yarn.lock",
    "build", "dist",
]

paths_to_delete = []
for p in raw_paths_to_delete:
    resolved_path = Path(p).resolve()
    if resolved_path != active_venv_path:
        paths_to_delete.append(resolved_path)
    else:
        print(f"⚠️  Skipping active venv: {resolved_path}")

for path in paths_to_delete:
    if path.exists():
        print(f"🗑️  Found {path}...")
        try:
            if args.dry_run:
                print(f"💡 Would delete: {path}")
            elif args.yes or input(f"Delete {path}? [y/N]: ").lower() == "y":
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                print(f"✅ Deleted: {path}")
            else:
                print(f"⏭️  Skipped: {path}")
        except Exception as e:
            print(f"❌ Failed to remove {path}: {e}")

# Delete __pycache__, .pyc files, .pytest_cache recursively
print("🧹 Cleaning up __pycache__, .pyc files, and .pytest_cache...")
for root, dirs, files in os.walk("."):
    for dir_name in dirs:
        if dir_name in ["__pycache__", ".pytest_cache"]:
            full_path = Path(root) / dir_name
            print(f"🗑️  Removing {full_path}...")
            try:
                shutil.rmtree(full_path)
            except Exception as e:
                print(f"❌ Failed to remove directory {full_path}: {e}")

    for file_name in files:
        if file_name.endswith(".pyc"):
            full_path = Path(root) / file_name
            print(f"🗑️  Removing {full_path}...")
            try:
                full_path.unlink()
            except Exception as e:
                print(f"❌ Failed to remove file {full_path}: {e}")

print("✅ Cleanup complete.")