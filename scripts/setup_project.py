#!/usr/bin/env python3
"""
Robust project setup script for Manifest
Handles Python virtual environment, dependencies, Node.js setup, and environment validation
"""

import shutil
import os
import subprocess
import sys
import urllib.request
import ssl
import time
import json
from pathlib import Path
import re
import platform
from typing import Optional, List, Tuple

# Import utils with fallback
try:
    from utils import get_project_root
except ImportError:
    def get_project_root():
        """Fallback project root detection"""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if parent.name == "scripts":
                return parent.parent
        return current.parent.parent

PROJECT_ROOT = get_project_root()

class SetupError(Exception):
    """Custom exception for setup errors"""
    pass

class SetupLogger:
    """Enhanced logging with colors and status tracking"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.success_count = 0
    
    def info(self, message: str):
        print(f"ℹ️  {message}")
    
    def success(self, message: str):
        print(f"✅ {message}")
        self.success_count += 1
    
    def warning(self, message: str):
        print(f"⚠️  {message}")
        self.warnings.append(message)
    
    def error(self, message: str):
        print(f"❌ {message}")
        self.errors.append(message)
    
    def step(self, message: str):
        print(f"\n🔧 {message}")
        print("=" * 50)
    
    def summary(self):
        print(f"\n📊 Setup Summary:")
        print(f"✅ Successful steps: {self.success_count}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        if self.errors:
            print("\n❌ Errors:")
            for error in self.errors:
                print(f"   - {error}")
            return False
        return True

logger = SetupLogger()

def is_broken_venv() -> bool:
    """Check if current Python is from a broken virtual environment"""
    venv_marker = os.path.join(os.getcwd(), ".venv")
    current_python = sys.executable
    return venv_marker in current_python and not os.path.exists(current_python)

def reinvoke_with_system_python():
    """Reinvoke script with system Python if in broken venv"""
    if os.environ.get("SETUP_PROJECT_REINVOKED") == "1":
        return
    
    if is_broken_venv():
        logger.warning("Detected broken .venv. Reinvoking with system Python...")
        system_python = shutil.which("python") or shutil.which("python3")
        if system_python:
            new_env = os.environ.copy()
            new_env["SETUP_PROJECT_REINVOKED"] = "1"
            try:
                subprocess.run([system_python, __file__], env=new_env, check=True)
                sys.exit(0)
            except subprocess.CalledProcessError:
                logger.error("Failed to reinvoke with system Python")
                sys.exit(1)
        else:
            logger.error("Could not find system Python interpreter")
            sys.exit(1)

def run_cmd_with_retry(cmd: List[str], cwd: Optional[str] = None, max_retries: int = 3, 
                      timeout: int = 300) -> bool:
    """Run command with retry logic and better error handling"""
    executable = cmd[0]
    
    # Handle npm path issues on macOS
    if executable == "npm" and shutil.which("npm") is None:
        homebrew_npm = "/opt/homebrew/bin/npm"
        if os.path.isfile(homebrew_npm) and os.access(homebrew_npm, os.X_OK):
            executable = homebrew_npm
            cmd = [executable] + cmd[1:]
    
    # Check if executable exists
    if not (os.path.isfile(executable) and os.access(executable, os.X_OK)) and shutil.which(executable) is None:
        logger.error(f"Cannot execute: {cmd[0]}")
        return False
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Running: {' '.join(cmd)} in {cwd or os.getcwd()} (attempt {attempt + 1})")
            result = subprocess.run(
                cmd, 
                cwd=cwd, 
                check=True, 
                timeout=timeout,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                logger.info(f"Output: {result.stdout.strip()}")
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {timeout}s (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                logger.error(f"Command failed after {max_retries} attempts due to timeout")
                return False
        except subprocess.CalledProcessError as e:
            logger.warning(f"Command failed (attempt {attempt + 1}): {e}")
            if e.stderr:
                logger.warning(f"Error output: {e.stderr}")
            if attempt == max_retries - 1:
                logger.error(f"Command failed after {max_retries} attempts")
                return False
            time.sleep(2 ** attempt)  # Exponential backoff
    
    return False

def download_with_retry(url: str, dest_path: str, max_retries: int = 3) -> bool:
    """Download file with retry logic and SSL context"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading {url} (attempt {attempt + 1})")
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(url, context=ssl_context) as response:
                with open(dest_path, 'wb') as f:
                    shutil.copyfileobj(response, f)
            return True
        except Exception as e:
            logger.warning(f"Download failed (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to download {url} after {max_retries} attempts")
                return False
            time.sleep(2 ** attempt)
    return False

def bootstrap_pip_with_getpip(venv_path: str, python_executable: str) -> bool:
    """Bootstrap pip using get-pip.py with enhanced error handling"""
    getpip_url = "https://bootstrap.pypa.io/get-pip.py"
    getpip_path = os.path.join(venv_path, "get-pip.py")
    
    logger.info("Attempting to bootstrap pip using get-pip.py...")
    
    if not download_with_retry(getpip_url, getpip_path):
        return False
    
    try:
        success = run_cmd_with_retry([python_executable, getpip_path], cwd=venv_path)
        if success:
            logger.success("Successfully bootstrapped pip with get-pip.py")
        return success
    finally:
        if os.path.exists(getpip_path):
            os.remove(getpip_path)

def ensure_clean_venv() -> str:
    """Create and ensure a clean virtual environment with pip"""
    backend_path = "backend"
    venv_path = os.path.join(backend_path, ".venv")
    
    logger.step("Setting up Python virtual environment")
    
    # Check if venv exists but is broken
    if os.path.exists(venv_path):
        pip_path = os.path.join(venv_path, "bin", "pip") if os.name != "nt" else os.path.join(venv_path, "Scripts", "pip.exe")
        python_path = os.path.join(venv_path, "bin", "python") if os.name != "nt" else os.path.join(venv_path, "Scripts", "python.exe")
        
        if not os.path.exists(pip_path) or not os.path.exists(python_path):
            logger.warning("Existing venv is broken. Deleting and recreating...")
            shutil.rmtree(venv_path)
    
    # Create venv if it doesn't exist
    if not os.path.exists(venv_path):
        logger.info("Creating new virtual environment...")
        if not run_cmd_with_retry([sys.executable, "-m", "venv", ".venv"], cwd=backend_path):
            raise SetupError("Failed to create virtual environment")
    
    # Determine Python executable in venv - robust detection
    python_executable = None
    venv_bin_path = os.path.join(venv_path, "bin") if os.name != "nt" else os.path.join(venv_path, "Scripts")
    
    if os.path.exists(venv_bin_path):
        for entry in os.listdir(venv_bin_path):
            if re.match(r'^python(\d(\.\d+)?)?(\.exe)?$', entry):
                candidate_path = os.path.abspath(os.path.join(venv_bin_path, entry))
                if os.access(candidate_path, os.X_OK):
                    python_executable = candidate_path
                    break
    
    if not python_executable:
        raise SetupError(f"Could not find a valid Python executable in virtual environment at {venv_bin_path}")
    
    logger.info(f"Using Python executable: {python_executable}")
    
    # Ensure pip is available
    pip_path = os.path.join(venv_bin_path, "pip") if os.name != "nt" else os.path.join(venv_bin_path, "pip.exe")
    
    if not os.path.exists(pip_path):
        logger.info("pip not found. Installing with ensurepip...")
        if not run_cmd_with_retry([python_executable, "-m", "ensurepip", "--upgrade"], cwd=backend_path):
            logger.warning("ensurepip failed, trying get-pip.py...")
            if not bootstrap_pip_with_getpip(venv_path, python_executable):
                raise SetupError("Failed to install pip in virtual environment")
    
    # Verify pip works
    if not run_cmd_with_retry([python_executable, "-m", "pip", "--version"], cwd=backend_path):
        raise SetupError("pip verification failed")
    
    logger.success(f"Virtual environment ready at {venv_path}")
    return python_executable

def install_python_dependencies(python_executable: str) -> bool:
    """Install Python dependencies with comprehensive error handling"""
    backend_path = "backend"
    requirements_file = os.path.join(backend_path, "requirements.txt")
    
    logger.step("Installing Python dependencies")
    
    if not os.path.exists(requirements_file):
        logger.error(f"Requirements file not found: {requirements_file}")
        return False
    
    # Upgrade pip first
    logger.info("Upgrading pip...")
    if not run_cmd_with_retry([python_executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=backend_path):
        logger.warning("Failed to upgrade pip, continuing anyway...")
    
    # Install requirements
    logger.info("Installing requirements...")
    abs_requirements = os.path.abspath(requirements_file)
    if not run_cmd_with_retry([python_executable, "-m", "pip", "install", "-r", abs_requirements], cwd=backend_path):
        return False
    
    # Ensure critical packages are installed
    critical_packages = ["uvicorn", "fastapi", "python-dotenv", "requests", "supabase", "python-socketio"]
    for package in critical_packages:
        logger.info(f"Ensuring {package} is installed...")
        if not run_cmd_with_retry([python_executable, "-m", "pip", "install", package], cwd=backend_path):
            logger.warning(f"Failed to install {package}")
    
    return True

def verify_python_imports(python_executable: str) -> bool:
    """Verify that critical Python packages can be imported"""
    logger.step("Verifying Python imports")
    
    critical_imports = [
        "uvicorn", "fastapi", "dotenv", "requests", "supabase", 
        "socketio", "pydantic", "httpx", "openai"
    ]
    
    all_success = True
    for pkg in critical_imports:
        try:
            result = subprocess.run(
                [python_executable, "-c", f"import {pkg}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.success(f"Import check passed for '{pkg}'")
            else:
                logger.warning(f"Could not import '{pkg}': {result.stderr}")
                all_success = False
        except Exception as e:
            logger.warning(f"Import check failed for '{pkg}': {e}")
            all_success = False
    
    return all_success

def install_node_dependencies() -> bool:
    """Install Node.js dependencies with comprehensive fallbacks"""
    frontend_path = "frontend"
    
    logger.step("Installing Node.js dependencies")
    
    # Check for package.json
    package_json = os.path.join(frontend_path, "package.json")
    if not os.path.exists(package_json):
        logger.error(f"package.json not found in {frontend_path}")
        return False
    
    # Try npm first
    npm_path = shutil.which("npm")
    if npm_path:
        logger.info("Using npm to install dependencies...")
        if run_cmd_with_retry(["npm", "install"], cwd=frontend_path):
            return True
    
    # Try yarn
    yarn_path = shutil.which("yarn")
    if yarn_path:
        logger.info("Using yarn to install dependencies...")
        if run_cmd_with_retry(["yarn"], cwd=frontend_path):
            return True
    
    # Try to install Node.js if not found
    if not npm_path and not yarn_path:
        logger.warning("Neither npm nor yarn found. Attempting to install Node.js...")
        if install_nodejs():
            npm_path = shutil.which("npm")
            if npm_path and run_cmd_with_retry(["npm", "install"], cwd=frontend_path):
                return True
    
    logger.error("Failed to install Node.js dependencies")
    return False

def install_nodejs() -> bool:
    """Install Node.js using platform-specific methods"""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        return install_nodejs_macos()
    elif system == "linux":
        return install_nodejs_linux()
    elif system == "windows":
        return install_nodejs_windows()
    else:
        logger.error(f"Unsupported operating system: {system}")
        return False

def install_nodejs_macos() -> bool:
    """Install Node.js on macOS using Homebrew"""
    brew_path = shutil.which("brew")
    
    if not brew_path:
        logger.info("Installing Homebrew...")
        try:
            subprocess.run([
                '/bin/bash', '-c',
                "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            ], check=True, timeout=600)
            
            # Update PATH for Homebrew
            homebrew_paths = [
                "/opt/homebrew/bin",
                "/usr/local/bin"
            ]
            for path in homebrew_paths:
                if path not in os.environ["PATH"]:
                    os.environ["PATH"] = f"{path}:{os.environ['PATH']}"
            
            brew_path = shutil.which("brew")
            if not brew_path:
                logger.error("Homebrew installation succeeded but brew command not found")
                return False
        except Exception as e:
            logger.error(f"Failed to install Homebrew: {e}")
            return False
    
    logger.info("Installing Node.js using Homebrew...")
    try:
        subprocess.run(["brew", "install", "node"], check=True, timeout=300)
        return True
    except Exception as e:
        logger.error(f"Failed to install Node.js: {e}")
        return False

def install_nodejs_linux() -> bool:
    """Install Node.js on Linux using NodeSource repository"""
    logger.info("Installing Node.js on Linux...")
    try:
        # Add NodeSource repository
        subprocess.run([
            "curl", "-fsSL", "https://deb.nodesource.com/setup_lts.x", "|", "sudo", "-E", "bash", "-"
        ], check=True, shell=True)
        
        # Install Node.js
        subprocess.run(["sudo", "apt-get", "install", "-y", "nodejs"], check=True)
        return True
    except Exception as e:
        logger.error(f"Failed to install Node.js on Linux: {e}")
        return False

def install_nodejs_windows() -> bool:
    """Install Node.js on Windows using winget or chocolatey"""
    logger.info("Installing Node.js on Windows...")
    
    # Try winget first
    winget_path = shutil.which("winget")
    if winget_path:
        try:
            subprocess.run(["winget", "install", "OpenJS.NodeJS"], check=True)
            return True
        except Exception:
            pass
    
    # Try chocolatey
    choco_path = shutil.which("choco")
    if choco_path:
        try:
            subprocess.run(["choco", "install", "nodejs"], check=True)
            return True
        except Exception:
            pass
    
    logger.error("Please install Node.js manually from https://nodejs.org/")
    return False

def create_env_template() -> bool:
    """Create a template .env file if it doesn't exist"""
    env_path = PROJECT_ROOT / ".env"
    
    if env_path.exists():
        logger.info(".env file already exists")
        return True
    
    logger.info("Creating .env template file...")
    
    template_content = """# Manifest Environment Configuration
# Replace these values with your actual API keys and configuration

# Supabase Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
SUPABASE_ANON_KEY=your_supabase_anon_key_here

# AI Configuration (OpenAI, optional for demo mode)
OPENAI_API_KEY=your_openai_api_key_here
AI_MODEL=gpt-4o-mini
VOICE_AGENT_MODEL=gpt-4o
VOICE_AGENT_TRANSCRIBE_MODEL=gpt-4o-transcribe
VOICE_AGENT_TTS_MODEL=tts-1
VOICE_AGENT_TTS_VOICE=nova
VOICE_LLM_MODEL=gpt-4.1
VOICE_STT_MODEL=gpt-4o-transcribe
VOICE_TTS_VOICE=coral

# Application Configuration
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# Server Configuration
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Database: leave unset for local demo (in-memory + demo auth). For Postgres, set a real URL:
# DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Email Configuration (optional)
SMTP_HOST=your_smtp_host_here
SMTP_PORT=587
SMTP_USER=your_smtp_user_here
SMTP_PASSWORD=your_smtp_password_here

# File Storage Configuration (optional)
STORAGE_BUCKET=your_storage_bucket_here
STORAGE_REGION=your_storage_region_here
"""
    
    try:
        with open(env_path, 'w') as f:
            f.write(template_content)
        logger.success("Created .env template file")
        logger.warning("Please update the .env file with your actual API keys and configuration")
        return True
    except Exception as e:
        logger.error(f"Failed to create .env template: {e}")
        return False

def validate_env_file() -> bool:
    """Validate .env file and required keys"""
    logger.step("Validating environment configuration")
    
    env_path = PROJECT_ROOT / ".env"
    
    if not env_path.exists():
        logger.warning(".env file not found")
        if create_env_template():
            logger.warning("Created .env template. Please update it with your actual values.")
            return False
        else:
            logger.error("Failed to create .env template")
            return False
    
    try:
        with open(env_path) as f:
            env_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read .env file: {e}")
        return False
    
    # External service keys are optional because the app can boot in demo mode
    optional_keys = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OPENAI_API_KEY"]
    missing_keys = []

    for key in optional_keys:
        if not re.search(rf"^{key}=.*", env_content, re.MULTILINE):
            missing_keys.append(key)

    if missing_keys:
        logger.warning(
            "Missing optional environment variables: "
            f"{', '.join(missing_keys)}"
        )
        logger.info(
            "Manifest can still run in demo mode without these keys. "
            "Add them later to enable live AI and Supabase integrations."
        )

    # Validate placeholder values and explain that they only block live integrations
    placeholder_warnings = []
    if "your_supabase_url_here" in env_content:
        placeholder_warnings.append("SUPABASE_URL contains placeholder value")
    if "your_supabase_service_role_key_here" in env_content:
        placeholder_warnings.append("SUPABASE_SERVICE_ROLE_KEY contains placeholder value")
    if "your_openai_api_key_here" in env_content:
        placeholder_warnings.append("OPENAI_API_KEY contains placeholder value")
    if re.search(r"^DATABASE_URL=your_database_url_here\s*$", env_content, re.MULTILINE):
        placeholder_warnings.append(
            "DATABASE_URL is still the template value — remove it or set a real URL (otherwise demo mode breaks)"
        )

    if placeholder_warnings:
        logger.warning("Environment validation issues found:")
        for error in placeholder_warnings:
            logger.warning(f"  - {error}")
        logger.info(
            "These only affect live integrations. Demo mode will still work."
        )

    logger.success("Environment configuration validated for demo mode startup")
    return True

def run_tests(python_executable: str) -> bool:
    """Run basic tests to verify setup"""
    logger.step("Running basic tests")
    
    # Test Python backend
    backend_path = "backend"
    if os.path.exists(python_executable):
        logger.info("Testing Python backend...")
        if run_cmd_with_retry([python_executable, "-m", "pytest", "--version"], cwd=backend_path):
            logger.success("Python backend tests available")
        else:
            logger.warning(f"Python backend tests not available (python_executable: {python_executable}, cwd: {backend_path})")
    else:
        logger.warning(f"Python executable not found for backend tests: {python_executable}")
    
    # Test Node.js frontend
    frontend_path = "frontend"
    if os.path.exists(os.path.join(frontend_path, "node_modules")):
        logger.info("Testing Node.js frontend...")
        npm_path = shutil.which("npm")
        if npm_path and run_cmd_with_retry(["npm", "test", "--", "--passWithNoTests"], cwd=frontend_path):
            logger.success("Node.js frontend tests passed")
        else:
            logger.warning(f"Node.js frontend tests failed or not available (cwd: {frontend_path})")
    
    return True

def main():
    """Main setup function with comprehensive error handling"""
    print("🚀 Manifest Project Setup")
    print("=" * 50)
    
    try:
        # Check for broken venv and reinvoke if needed
        reinvoke_with_system_python()
        
        # Step 1: Set up Python virtual environment
        python_executable = ensure_clean_venv()
        
        # Step 2: Install Python dependencies
        if not install_python_dependencies(python_executable):
            raise SetupError("Failed to install Python dependencies")
        
        # Step 3: Verify Python imports
        if not verify_python_imports(python_executable):
            logger.warning("Some Python imports failed, but continuing...")
        
        # Step 4: Install Node.js dependencies
        if not install_node_dependencies():
            logger.warning("Node.js dependency installation failed, but continuing...")
        
        # Step 5: Validate environment
        if not validate_env_file():
            logger.warning("Environment validation failed, but continuing...")
        
        # Step 6: Run basic tests
        run_tests(python_executable)
        
        # Final summary
        if logger.summary():
            print("\n🎉 Setup completed successfully!")
            print("\nNext steps:")
            print("1. Update your .env file with actual API keys")
            print("2. Start the backend: cd backend && source .venv/bin/activate && python -m uvicorn app.main:app --reload")
            print("3. Start the frontend: cd frontend && npm start")
            print("\nFor more information, see the README.md file.")
        else:
            print("\n⚠️  Setup completed with warnings/errors.")
            print("Please review the issues above and fix them before running the application.")
            sys.exit(1)
            
    except SetupError as e:
        logger.error(f"Setup failed: {e}")
        logger.summary()
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n❌ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.summary()
        sys.exit(1)

if __name__ == "__main__":
    main()
