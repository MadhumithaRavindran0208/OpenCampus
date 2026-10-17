"""
Writes a timestamped, human-readable crash report file instead of
letting an unhandled exception's traceback vanish into a terminal that
may get closed before anyone reads it.

This is the version used for in-request crashes (see the Exception
handler registered in app/__init__.py::create_app). main.py has its own
small, standalone copy of the same logic for startup-time crashes,
deliberately duplicated rather than imported from here -- importing
anything under the `app` package requires Flask to already be
importable (app/__init__.py imports it at module level), so this
module can't be safely used before main.py has confirmed dependencies
are installed. Keep both copies in sync if the report format changes.
"""
from __future__ import annotations

import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def write_crash_report(exc: BaseException, context: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    report_path = reports_dir / f"crash_{timestamp}.md"

    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    content = "\n".join([
        "# OpenCampus OSS Crash Report",
        "",
        f"- **When**: `{datetime.now(timezone.utc).isoformat()} UTC`",
        f"- **Context**: `{context}`",
        f"- **Python Version**: `{sys.version.split()[0]} ({platform.python_implementation()})`",
        f"- **OS**: `{platform.platform()}`",
        "",
        "## Traceback",
        "```python",
        tb_str.strip(),
        "```",
        ""
    ])
    report_path.write_text(content, encoding="utf-8")
    return report_path