"""conftest.py — add 03-development/ to sys.path so tests can import from src.*"""
import sys
from pathlib import Path

_dev = Path(__file__).parent.parent / "03-development"
if str(_dev) not in sys.path:
    sys.path.insert(0, str(_dev))
