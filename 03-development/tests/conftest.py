import sys
from pathlib import Path

_dev = Path(__file__).parent.parent
if str(_dev) not in sys.path:
    sys.path.insert(0, str(_dev))
