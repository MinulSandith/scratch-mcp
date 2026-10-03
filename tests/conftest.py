import json
import shutil
import zipfile
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample.sb3"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    projects = tmp_path / "ScratchProjects"
    projects.mkdir()
    shutil.copy(SAMPLE, projects / "sample.sb3")
    return projects


class Tools:
    """Old flat method names over the group actions (keeps the early tests readable)."""

    def __init__(self, ctx):
        self.ctx, self.ws = ctx, ctx.ws

    def _open(self, project):
        return call(self.ctx, "project_manager", "open", name=project)

    def list_projects(self):
        return call(self.ctx, "project_manager", "list")

    def read_project(self, project):
        self._open(project)
        return call(self.ctx, "project_manager", "summary")

    def get_project_json(self, project, pretty=True):
        self._open(project)
        text = call(self.ctx, "inspection_manager", "json", pretty=pretty, max_chars=10**9)["json"]
        return text

    def save_project_json(self, project, project_json):
        self._open(project)
        return call(self.ctx, "project_manager", "save_json", project_json=project_json)

    def create_project(self, name, sprite_name="Sprite1"):
        return call(self.ctx, "project_manager", "create", name=name, sprite_name=sprite_name)

    def add_script(self, project, sprite, script, x=None, y=None):
        self._open(project)
        args = {k: v for k, v in dict(sprite=sprite, script=script, x=x, y=y).items() if v is not None}
        return call(self.ctx, "script_manager", "add_text", **args)


@pytest.fixture
def tools(ctx) -> Tools:
    return Tools(ctx)


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
