#!/usr/bin/env python3
"""
Manifest Application Stop Script
Stops both backend and frontend services cleanly
"""

import subprocess
import sys
from pathlib import Path

def get_project_root():
    """Get project root directory"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "scripts":
            return parent.parent
    return current.parent.parent

def stop_services():
    """Stop running services"""
    print("🛑 Stopping Manifest services...")
    
    # Kill processes on common ports
    ports_to_kill = [8000, 3000]
    
    for port in ports_to_kill:
        try:
            # Find processes using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"Stopping process {pid} on port {port}")
                        subprocess.run(["kill", "-TERM", pid], check=False)
                        # Wait a moment then force kill if needed
                        subprocess.run(["sleep", "2"], check=False)
                        subprocess.run(["kill", "-KILL", pid], check=False)
            else:
                print(f"No process found on port {port}")
                
        except Exception as e:
            print(f"Warning: Could not stop processes on port {port}: {e}")
    
    print("✅ Services stopped")

def main():
    """Main function"""
    stop_services()

if __name__ == "__main__":
    main() 