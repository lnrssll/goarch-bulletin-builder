import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE_DIRS = ("data", "assets", "templates", "static")


@pytest.fixture
def site(tmp_path, monkeypatch) -> Path:
    """A copy of the repo root with empty build/ and archive/, as the working directory."""
    for path in ROOT.glob("*.typ"):
        shutil.copy(path, tmp_path)
    for name in SITE_DIRS:
        shutil.copytree(ROOT / name, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    return tmp_path
