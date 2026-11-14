#!/bin/bash

# Start backend (serves both API and pre-built frontend)
# Use PORT env var if set (deployment uses 3000), default to 5000 for development
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5000}
