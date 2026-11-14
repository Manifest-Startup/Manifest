"""
Manifest MCP Server - Transform ideas into investor-ready startups via AI agents.

This MCP server exposes Manifest's functionality to AI agents, enabling them to:
- Create and manage startup ideas
- Generate business documents (BMC, pitch decks, PRDs, patents)
- Manage investments and social interactions
- Discover and explore the ideas marketplace

Usage:
    # Run as STDIO server (default)
    manifest-mcp

    # Run as HTTP/SSE server
    manifest-mcp --transport sse --port 8080
"""

__version__ = "1.0.0"
__all__ = ["create_server", "ManifestClient"]

from .client import ManifestClient
from .server import create_server
