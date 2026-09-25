"""Start Ghost Job in a native desktop window (reflex-desktop).

Usage (from repo root)::

    uv run python -m job
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    # Reflex discovers rxconfig.py in the process cwd.
    from reflex_desktop.cli import main as desktop_main

    desktop_main(["dev", *sys.argv[1:]], prog_name="reflex-desktop")


if __name__ == "__main__":
    main()
