"""Shared state handed to every action handler."""

from __future__ import annotations

import os
from typing import Any

from .library import Library
from .store import ProjectStore, Session
from .workspace import Workspace, WorkspaceError


class Ctx:
    def __init__(self, root: str | os.PathLike[str]):
        self.ws = Workspace(root)
        self.store = ProjectStore(self.ws)
        self._runtime: Any = None
        self._browser: Any = None
        self.library = Library()
        self.audio_clipboard: bytes | None = None
        self.clipboard: list[str] = []  # copied vector elements (costume_manager copy/paste)

    @property
    def browser(self):
        if self._browser is None:
            from .runtime.browser import BrowserService

            self._browser = BrowserService()
        return self._browser

    @property
    def runtime(self):
        if self._runtime is None:
            from .runtime.manager import RuntimeManager

            self._runtime = RuntimeManager(self)
        return self._runtime

    # -- helpers used by handlers -----------------------------------------

    def session(self, project: str | None) -> Session:
        return self.store.get(project)

    def sprite_name(self, session: Session, sprite: str | None) -> str:
        """Explicit sprite name, else the selected sprite."""
        name = sprite or session.selected_sprite
        if not name:
            raise WorkspaceError("No sprite given and none is selected. Pass 'sprite' or call sprite_manager select.")
        return name

    def target(self, data: dict[str, Any], session: Session, sprite: str | None) -> dict[str, Any]:
        from .editing import EditError, find_target

        name = self.sprite_name(session, sprite)
        try:
            return find_target(data, name)
        except EditError as exc:
            raise WorkspaceError(str(exc)) from exc
