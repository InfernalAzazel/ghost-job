"""Start Ghostjob via Reflex.

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
    sys.argv = ["reflex", "run", *sys.argv[1:]]
    from reflex.reflex import cli

    cli()


if __name__ == "__main__":
    main()
