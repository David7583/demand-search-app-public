"""Run the S2 backend on loopback only, using this project's interpreter."""

import argparse
import sys
from pathlib import Path

from check_environment import require_project_environment

ROOT = Path(__file__).resolve().parents[1]
require_project_environment()
sys.path.insert(0, str(ROOT / "apps/server/src"))

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(
        "demand_search.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
    )
