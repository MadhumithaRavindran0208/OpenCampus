"""
Alternate entry point:

    python run.py

Prefer `python main.py` directly -- this file exists only for anyone
already in the habit of `python run.py` as the convention. It's now a
thin wrapper around main.py, so dependency checks, the
port-availability check, first-run demo seeding, production-server
selection, and startup crash reporting all happen identically no
matter which of the two you run. There is no separate logic here to
drift out of sync with main.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from main import run_with_crash_reporting

    run_with_crash_reporting()