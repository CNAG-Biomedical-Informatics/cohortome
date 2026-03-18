import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / ".deps"

for path in (str(DEPS), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
