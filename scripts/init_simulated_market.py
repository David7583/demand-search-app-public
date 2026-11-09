"""Initialize only the independent synthetic store; --rebuild is explicit and destructive."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/server/src"))

from demand_search.config import Settings  # noqa: E402
from demand_search.simulated_market import initialize_market  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Explicitly replace ONLY simulated-market.sqlite3 with the fixed seed",
    )
    args = parser.parse_args()
    path = initialize_market(Settings.from_env(), rebuild=args.rebuild)
    print(f"SYNTHETIC market verified: 500 merchants / 1500 offerings: {path}")


if __name__ == "__main__":
    main()
