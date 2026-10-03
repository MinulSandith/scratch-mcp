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


@pytest.fixture
def ctx(root: Path):
    from scratch_mcp.ctx import Ctx
    import scratch_mcp.server  # noqa: F401  (registers groups)
    from scratch_mcp.server import GROUP_MODULES
    import importlib

    for mod in GROUP_MODULES:
        importlib.import_module(f"scratch_mcp.groups.{mod}")
    return Ctx(root)


def call(ctx, group: str, action: str, /, **args):
    """Run an action the way the MCP tool does; returns the handler's result (raises on error)."""
    import anyio

    from scratch_mcp import registry

    async def run():
        return await registry.dispatch(group, ctx, action, args)

    return anyio.run(run)
