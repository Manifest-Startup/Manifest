"""Static files the backend ships with (they are inside the Docker image).

Use :data:`ASSETS_DIR` instead of paths relative to a module, so moving a
module never breaks how an asset is found.
"""

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
