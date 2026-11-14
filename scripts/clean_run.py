import subprocess
import sys
import os
import signal
import threading
import time
from pathlib import Path
import shutil
from utils import get_project_root
from dotenv import dotenv_values

PROJECT_ROOT = get_project_root()
BACKEND_PATH = PROJECT_ROOT / "backend"
FRONTEND_PATH = PROJECT_ROOT / "frontend"
PYTHON = sys.executable
SCRIPTS_PATH = PROJECT_ROOT / "scripts"

REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]

def precheck_env():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        print(f"❌ .env file not found at {env_path}. Backend will not start.")
        sys.exit(1)
    with open(env_path) as f:
        lines = f.readlines()
    env_dict = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env_dict[k.strip()] = v.strip()
    missing = [k for k in REQUIRED_ENV_VARS if not env_dict.get(k)]
    if missing:
        print(f"❌ The following required environment variables are missing or empty in .env: {', '.join(missing)}")
        sys.exit(1)
    print(f"✅ .env file and required environment variables found.")


def run_clean():
    print("\n🧹 Cleaning project...")
    result = subprocess.run([PYTHON, str(SCRIPTS_PATH / "clean_project.py"), "--yes"], check=False)
    if result.returncode != 0:
        print("❌ Cleaning failed.")
        sys.exit(1)


def run_setup():
    print("\n🔧 Setting up project dependencies...")
    result = subprocess.run([PYTHON, str(SCRIPTS_PATH / "setup_project.py")], check=False)
    if result.returncode != 0:
        print("❌ Setup failed.")
        sys.exit(1)


def run_backend():
    print("\n🚀 Starting FastAPI backend...")
    venv_python = BACKEND_PATH / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if not venv_python.exists():
        print(f"❌ Backend venv not found at {venv_python}. Did setup fail?")
        sys.exit(1)
    app_path = BACKEND_PATH / "app" / "main.py"
    if not app_path.exists():
        print(f"❌ Backend entrypoint not found at {app_path}")
        sys.exit(1)
    # Set PYTHONPATH to backend to ensure 'app' is importable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_PATH)
    # Load .env and inject variables
    dotenv_path = PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        env_vars = dotenv_values(dotenv_path)
        env.update(env_vars)
        print("[DEBUG] Injected .env variables into backend environment:")
        for var in REQUIRED_ENV_VARS:
            print(f"[DEBUG] {var}={env.get(var)}")
    else:
        print(f"[DEBUG] .env file not found at {dotenv_path}")
    # Run uvicorn with correct PYTHONPATH and env
    return subprocess.Popen([
        str(venv_python), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"
    ], cwd=BACKEND_PATH, env=env)


def run_frontend():
    print("\n🚀 Starting React frontend...")
    # Prefer npm, fallback to yarn
    npm_path = shutil.which("npm")
    yarn_path = shutil.which("yarn")
    if npm_path:
        cmd = ["npm", "start"]
    elif yarn_path:
        cmd = ["yarn", "start"]
    else:
        print("❌ Neither npm nor yarn found. Please install Node.js.")
        sys.exit(1)
    return subprocess.Popen(cmd, cwd=FRONTEND_PATH)


def stream_logs(proc, name):
    for line in iter(proc.stdout.readline, b""):
        print(f"[{name}] {line.decode().rstrip()}")


def main():
    precheck_env()
    run_clean()
    run_setup()

    # Start backend and frontend
    backend_proc = run_backend()
    frontend_proc = run_frontend()

    procs = [(backend_proc, "backend"), (frontend_proc, "frontend")]

    def shutdown(*_):
        print("\n🛑 Shutting down...")
        for proc, name in procs:
            if proc.poll() is None:
                print(f"Killing {name}...")
                proc.terminate()
        # Wait for processes to exit
        for proc, _ in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("✅ All processes stopped.")
        sys.exit(0)

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            # Check if any process exited
            for proc, name in procs:
                if proc.poll() is not None:
                    print(f"❌ {name} exited unexpectedly with code {proc.returncode}")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()

if __name__ == "__main__":
    main() 