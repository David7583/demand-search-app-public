"""Refuse linked/shared environments before imports or dependency installation."""

import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_project_environment():
    expected = ROOT / ".venv"
    if expected.resolve() != expected or Path(sys.prefix).resolve() != expected:
        raise RuntimeError("Use this project's physical .venv; linked environments are not allowed")
    if sys.version_info[:3] != (3, 12, 7):
        raise RuntimeError("CPython 3.12.7 required")
    config = dict(
        line.lower().strip().split(" = ", 1)
        for line in (expected / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
        if " = " in line
    )
    if config.get("include-system-site-packages") != "false" or site.ENABLE_USER_SITE:
        raise RuntimeError("Global/user site packages must be disabled")


if __name__ == "__main__":
    require_project_environment()
    print("Independent project environment: PASS")
