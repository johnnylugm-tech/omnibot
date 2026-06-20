"""Run ruff via Python library."""
import json
import sys

# Try to import ruff's internal modules
try:
    import ruff
    print("ruff module imported:", ruff)
except Exception as e:
    print("Error importing ruff:", e)
