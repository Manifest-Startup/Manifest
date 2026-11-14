# Manifest Scripts

This directory contains utility scripts for managing the Manifest application.

## Quick Start

### Start the Application
```bash
# From the project root
manifest-dev start

# Or make it executable and run directly
chmod +x scripts/start_app.py
./scripts/start_app.py
```

### Stop the Application
```bash
# From the project root
manifest-dev stop

# Or make it executable and run directly
chmod +x scripts/stop_app.py
./scripts/stop_app.py
```

### Bootstrap the Workspace
```bash
# From the project root
manifest-dev setup

# Or use the shell wrapper directly
bash scripts/bootstrap.sh
```

## Scripts Overview

### `start_app.py`
- **Purpose**: Starts both backend and frontend services
- **Features**:
  - Checks for all prerequisites (Python, Node.js, npm, virtual environment, dependencies)
  - Automatically runs setup if dependencies are missing
  - Provides detailed error messages and status updates
  - Monitors both services and displays their output
  - Handles graceful shutdown with Ctrl+C

### `stop_app.py`
- **Purpose**: Stops all running services cleanly
- **Features**:
  - Kills processes on ports 8000 (backend) and 3000 (frontend)
  - Uses graceful termination first, then force kill if needed

### `setup_project.py`
- **Purpose**: Sets up the development environment
- **Features**:
  - Creates Python virtual environment
  - Installs Python dependencies
  - Installs Node.js dependencies
  - Creates .env file template
  - Runs tests to verify setup

## Troubleshooting

### Common Issues

1. **"Python not found"**
   - Install Python 3.8+ from python.org or use your system package manager

2. **"Node.js not found"**
   - Install Node.js from nodejs.org or use your system package manager

3. **"Backend virtual environment not found"**
   - Run `python3 scripts/setup_project.py` to create the virtual environment

4. **"Frontend dependencies not found"**
   - Run `python3 scripts/setup_project.py` to install npm dependencies

5. **"Port already in use"**
   - Run `python3 scripts/stop_app.py` to stop existing services
   - Or manually kill processes: `lsof -ti:8000 | xargs kill` and `lsof -ti:3000 | xargs kill`

### Manual Setup

If the automatic setup fails, you can run these commands manually:

```bash
# Backend setup
cd backend
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd frontend
npm install

# Create .env file (if not exists)
cp .env.template .env  # Edit .env with your values
```

## Services

When running, the application provides:

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Interactive API Docs**: http://localhost:8000/redoc

## File Structure

```
scripts/
├── setup_project.py    # Main setup script
├── start_app.py        # Application startup script
├── stop_app.py         # Application stop script
└── README.md          # This file
```

## Contributing

When modifying these scripts:

1. **Test on multiple platforms** (macOS, Linux, Windows)
2. **Add proper error handling** for all operations
3. **Include retry logic** for network operations
4. **Update this README** with any new features or changes
5. **Test with different Python/Node.js versions**

## License

These scripts are part of the Manifest project and follow the same license terms. 