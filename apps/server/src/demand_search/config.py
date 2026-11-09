"""Independent local settings. Hosted deployment is deliberately unavailable."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    mode: str = "local-dev"
    data_dir: Path = ROOT / "runtime"

    def __post_init__(self):
        if self.mode != "local-dev":
            raise ValueError("HOSTED_NOT_IMPLEMENTED")
        resolved = self.data_dir.resolve()
        if not resolved.is_relative_to(ROOT / "runtime"):
            raise ValueError("DATA_DIRECTORY_OUTSIDE_PROJECT_RUNTIME")
        object.__setattr__(self, "data_dir", resolved)

    @classmethod
    def from_env(cls):
        subdir = os.environ.get("DSA_DATA_SUBDIR", "")
        if subdir and not re.fullmatch(r"test-[a-z0-9-]{1,60}", subdir):
            raise ValueError("ONLY_EXPLICIT_TEST_DATA_SUBDIRECTORIES_ALLOWED")
        return cls(
            mode=os.environ.get("DSA_MODE", "local-dev"),
            data_dir=ROOT / "runtime" / subdir,
        )

    @property
    def database(self):
        return self.data_dir / "demand-search.sqlite3"
