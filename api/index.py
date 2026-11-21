import os
import sys
from pathlib import Path

# Add backend directory and project root to sys.path so app modules are resolved properly on Vercel
_current = Path(__file__).resolve().parent
_root = _current.parent
_backend = _root / "backend"

for path in (_backend, _root, _current):
    ps = str(path)
    if ps not in sys.path:
        sys.path.insert(0, ps)

try:
    from app.main import app
except ImportError:
    from backend.app.main import app
