#!/usr/bin/env python3
"""
Manifest Application Startup Script
Starts both backend and frontend services with robust error handling
"""

import os
import subprocess
import sys
import time
import signal
import threading
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

def get_project_root():
    """Get project root directory"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "scripts":
            return parent.parent
    return current.parent.parent

PROJECT_ROOT = get_project_root()

class AppStarter:
    """Manages starting and stopping the application services"""
    
    def __init__(self):
        self.backend_process = None
        self.frontend_process = None
        self.running = False
        self.process_outputs = {"backend": [], "frontend": []}

    def _report_startup_failure(self, process: Optional[subprocess.Popen], service_name: str):
        if not process or not process.stdout:
            return

        try:
            output = process.stdout.read().strip()
        except Exception as exc:
            print(f"⚠️  Unable to read {service_name} startup output: {exc}")
            return

        if output:
            print(f"----- {service_name.upper()} STARTUP OUTPUT -----")
            print(output)
            print("----- END STARTUP OUTPUT -----")
        
    def check_prerequisites(self) -> Dict[str, bool]:
        """Check if all prerequisites are met"""
        checks = {
            "python": False,
            "node": False,
            "npm": False,
            "backend_venv": False,
            "frontend_deps": False,
        }
        
        # Check Python
        python_cmd = shutil.which("python3") or shutil.which("python")
        if python_cmd:
            checks["python"] = True
            print(f"✅ Python found: {python_cmd}")
        else:
            print("❌ Python not found")
        
        # Check Node.js
        node_cmd = shutil.which("node")
        if node_cmd:
            checks["node"] = True
            print(f"✅ Node.js found: {node_cmd}")
        else:
            print("❌ Node.js not found")
        
        # Check npm
        npm_cmd = shutil.which("npm")
        if npm_cmd:
            checks["npm"] = True
            print(f"✅ npm found: {npm_cmd}")
        else:
            print("❌ npm not found")
        
        # Check backend virtual environment
        backend_path = PROJECT_ROOT / "backend"
        venv_python = backend_path / ".venv" / "bin" / "python"
        if os.name == "nt":  # Windows
            venv_python = backend_path / ".venv" / "Scripts" / "python.exe"
        
        if venv_python.exists():
            checks["backend_venv"] = True
            print("✅ Backend virtual environment found")
        else:
            print("❌ Backend virtual environment not found")
        
        # Check frontend dependencies
        frontend_path = PROJECT_ROOT / "frontend"
        node_modules = frontend_path / "node_modules"
        if node_modules.exists():
            checks["frontend_deps"] = True
            print("✅ Frontend dependencies found")
        else:
            print("❌ Frontend dependencies not found")
        
        # .env is optional: backend enables demo + in-memory DB when DATABASE_URL is unset
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            print("✅ .env file found")
        else:
            print("⚠️  .env file not found — OK for local demo; create one for Supabase, AI keys, and Postgres")
        
        return checks
    
    def setup_missing_dependencies(self, checks: Dict[str, bool]) -> bool:
        """Attempt to set up missing dependencies"""
        print("\n🔧 Attempting to set up missing dependencies...")
        
        if not checks["backend_venv"] or not checks["frontend_deps"]:
            print("Running setup script to install missing dependencies...")
            try:
                setup_script = PROJECT_ROOT / "scripts" / "setup_project.py"
                if setup_script.exists():
                    result = subprocess.run([sys.executable, str(setup_script)], 
                                          cwd=PROJECT_ROOT, 
                                          capture_output=True, 
                                          text=True)
                    if result.returncode == 0:
                        print("✅ Setup completed successfully")
                        return True
                    else:
                        print(f"❌ Setup failed: {result.stderr}")
                        return False
                else:
                    print("❌ Setup script not found")
                    return False
            except Exception as e:
                print(f"❌ Failed to run setup script: {e}")
                return False
        
        return True
    
    def start_backend(self) -> bool:
        """Start the FastAPI backend server"""
        backend_path = PROJECT_ROOT / "backend"
        venv_python = backend_path / ".venv" / "bin" / "python"
        
        if os.name == "nt":  # Windows
            venv_python = backend_path / ".venv" / "Scripts" / "python.exe"
        
        if not venv_python.exists():
            print("❌ Backend virtual environment not found.")
            return False
        
        print("🚀 Starting backend server...")
        try:
            # Check if uvicorn is available
            check_cmd = [str(venv_python), "-c", "import uvicorn; print('uvicorn available')"]
            result = subprocess.run(check_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ uvicorn not found in virtual environment")
                return False
            
            self.backend_process = subprocess.Popen(
                [str(venv_python), "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
                cwd=backend_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Wait and check if it starts successfully
            time.sleep(5)
            if self.backend_process.poll() is not None:
                print("❌ Backend failed to start")
                self._report_startup_failure(self.backend_process, "backend")
                return False
            
            print("✅ Backend server started on http://localhost:8000")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start backend: {e}")
            return False
    
    def start_frontend(self) -> bool:
        """Start the React frontend development server"""
        frontend_path = PROJECT_ROOT / "frontend"
        node_modules = frontend_path / "node_modules"
        
        if not node_modules.exists():
            print("❌ Frontend node_modules not found.")
            return False
        
        print("🚀 Starting frontend server...")
        try:
            # Check if npm start script exists
            package_json = frontend_path / "package.json"
            if not package_json.exists():
                print("❌ package.json not found")
                return False
            
            self.frontend_process = subprocess.Popen(
                ["npm", "start"],
                cwd=frontend_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env={**os.environ, "FAST_REFRESH": "false"}
            )
            
            # Wait and check if it starts successfully
            time.sleep(8)  # Frontend takes longer to start
            if self.frontend_process.poll() is not None:
                print("❌ Frontend failed to start")
                self._report_startup_failure(self.frontend_process, "frontend")
                return False
            
            print("✅ Frontend server started on http://localhost:3000")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start frontend: {e}")
            return False
    
    def monitor_processes(self):
        """Monitor and display output from both processes"""
        def monitor_backend():
            if self.backend_process:
                for line in iter(self.backend_process.stdout.readline, ''):
                    if line:
                        output = f"[BACKEND] {line.rstrip()}"
                        print(output)
                        self.process_outputs["backend"].append(output)
        
        def monitor_frontend():
            if self.frontend_process:
                for line in iter(self.frontend_process.stdout.readline, ''):
                    if line:
                        output = f"[FRONTEND] {line.rstrip()}"
                        print(output)
                        self.process_outputs["frontend"].append(output)
        
        backend_thread = threading.Thread(target=monitor_backend, daemon=True)
        frontend_thread = threading.Thread(target=monitor_frontend, daemon=True)
        
        backend_thread.start()
        frontend_thread.start()
    
    def stop_services(self):
        """Stop all running services"""
        print("\n🛑 Stopping services...")
        
        if self.backend_process:
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
            except Exception as e:
                print(f"Warning: Error stopping backend: {e}")
        
        if self.frontend_process:
            try:
                self.frontend_process.terminate()
                self.frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.frontend_process.kill()
            except Exception as e:
                print(f"Warning: Error stopping frontend: {e}")
        
        print("✅ Services stopped")
    
    def run(self):
        """Main run method"""
        print("🚀 Manifest Application Startup")
        print("=" * 50)
        
        # Check prerequisites
        checks = self.check_prerequisites()
        
        # Set up missing dependencies if needed
        if not all(checks.values()):
            if not self.setup_missing_dependencies(checks):
                print("\n❌ Failed to set up missing dependencies.")
                print("Please run 'python3 scripts/setup_project.py' manually and try again.")
                return False
            
            # Re-check after setup
            checks = self.check_prerequisites()
            if not all(checks.values()):
                print("\n❌ Some dependencies are still missing after setup.")
                return False
        
        # Start backend
        if not self.start_backend():
            print("\n❌ Failed to start backend. Check the logs above for details.")
            return False
        
        # Start frontend
        if not self.start_frontend():
            print("\n❌ Failed to start frontend. Stopping backend...")
            self.stop_services()
            return False
        
        self.running = True
        print("\n🎉 Application started successfully!")
        print("📱 Frontend: http://localhost:3000")
        print("🔧 Backend API: http://localhost:8000")
        print("📚 API Docs: http://localhost:8000/docs")
        print("\nPress Ctrl+C to stop all services")
        
        # Set up signal handlers
        def signal_handler(signum, frame):
            print(f"\n🛑 Received signal {signum}, shutting down...")
            self.stop_services()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start monitoring
        self.monitor_processes()
        
        # Keep running
        try:
            while self.running:
                time.sleep(1)
                # Check if processes are still running
                if self.backend_process and self.backend_process.poll() is not None:
                    print("❌ Backend process stopped unexpectedly")
                    self.running = False
                if self.frontend_process and self.frontend_process.poll() is not None:
                    print("❌ Frontend process stopped unexpectedly")
                    self.running = False
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_services()
        
        return True

def main():
    """Main function"""
    starter = AppStarter()
    success = starter.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 
