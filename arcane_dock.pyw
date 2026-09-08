"""Windowless launcher: pythonw arcane_dock.pyw (no console flash)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from arcanedock.app import main

sys.exit(main())
