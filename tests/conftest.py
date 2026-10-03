import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scratch_mcp.server import ScratchTools

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample.sb3"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    projects = tmp_path / "ScratchProjects"
    projects.mkdir()
    shutil.copy(SAMPLE, projects / "sample.sb3")
    return projects


@pytest.fixture
def tools(root: Path) -> ScratchTools:
    return ScratchTools(root)


def read_sb3(path: Path) -> tuple[dict, set[str]]:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read("project.json")), set(zf.namelist()) - {"project.json"}


def target(project: dict, name: str) -> dict:
    return next(t for t in project["targets"] if t["name"] == name)
