"""online_manager: READ-ONLY access to public Scratch projects. Kept separate from local editing."""

from __future__ import annotations

import json
from typing import Any

from ..ctx import Ctx
from ..library import ASSET_URL
from ..registry import GROUP_DOCS, action
from ..validate import validate_project
from ..workspace import WorkspaceError

G = "online_manager"
GROUP_DOCS[G] = (
    "Public, read-only Scratch website access: look up a shared project (title, author, stats, instructions, notes), a "
    "user's profile, and download a shared project as a local .sb3 you can edit. 'capabilities' lists what is and is NOT "
    "supported. NOT implemented, on purpose: logging in, saving/publishing to scratch.mit.edu, sharing/unsharing, remixing, "
    "posting comments, cloud variables. Scratch has no official, authorized API for those (only the website itself), and "
    "this server will not handle your Scratch password or session cookies or work around Scratch's security. To publish: "
    "export a .sb3 with export_manager and upload it yourself in the Scratch editor (File > Load from your computer, then Share)."
)

API = "https://api.scratch.mit.edu"
PROJECTS = "https://projects.scratch.mit.edu"


def _get_json(ctx: Ctx, url: str) -> Any:
    try:
        return json.loads(ctx.library.fetch(url).decode("utf-8"))
    except ValueError as exc:
        raise WorkspaceError(f"Unexpected response from {url}.") from exc


def _id(project_id: str | int) -> str:
    s = str(project_id).strip().rstrip("/")
    if "scratch.mit.edu/projects/" in s:
        s = s.split("/projects/")[1].split("/")[0]
    if not s.isdigit():
        raise WorkspaceError("project_id must be a number or a https://scratch.mit.edu/projects/<number> link.")
    return s


@action(G)
def capabilities(ctx: Ctx) -> dict:
    """What this group can and cannot do."""
    return {"supported": ["project_info (public metadata)", "import_project (download a shared project as .sb3)", "user_info (public profile)"],
            "not_supported": {
                "authenticate / log in": "Scratch offers no official OAuth/API login; storing passwords or cookies is out of scope.",
                "save to scratch.mit.edu": "Needs a logged-in session. Export a .sb3 and upload it in the editor.",
                "share / unshare": "Needs a logged-in session.", "remix": "Needs a logged-in session (and the original's remix permission).",
                "edit project instructions / notes": "Needs a logged-in session.", "cloud variables": "Cloud sync needs Scratch's cloud server and a logged-in account; the variables still exist locally.",
                "private or unshared projects": "Not downloadable without the owner's session."}}


@action(G)
def project_info(ctx: Ctx, project_id: str) -> dict:
    """Public metadata of a shared project: title, author, instructions, notes, dates, stats.

    Args:
        project_id: the number, or a scratch.mit.edu/projects/<n> link.
    """
    pid = _id(project_id)
    d = _get_json(ctx, f"{API}/projects/{pid}")
    return {"id": d.get("id"), "title": d.get("title"), "author": (d.get("author") or {}).get("username"),
            "instructions": d.get("instructions"), "description": d.get("description"), "public": d.get("public"),
            "remix": d.get("remix"), "history": d.get("history"), "stats": d.get("stats")}


@action(G)
def user_info(ctx: Ctx, username: str) -> dict:
    """Public profile of a Scratch user."""
    d = _get_json(ctx, f"{API}/users/{username.strip()}")
    return {"username": d.get("username"), "id": d.get("id"), "joined": (d.get("history") or {}).get("joined"),
            "bio": (d.get("profile") or {}).get("bio"), "status": (d.get("profile") or {}).get("status"), "country": (d.get("profile") or {}).get("country")}


@action(G)
def import_project(ctx: Ctx, project_id: str, name: str | None = None) -> dict:
    """Download a SHARED project (project.json + every costume/sound) as a new local project and open it. Scratch 2 (.sb2) projects are not supported.

    Args:
        project_id: the number or link.
        name: local name (default: 'scratch-<id>').
    """
    pid = _id(project_id)
    meta = _get_json(ctx, f"{API}/projects/{pid}")
    token = meta.get("project_token")
    if not token:
        raise WorkspaceError("This project has no download token (it may be unshared or private).")
    project = _get_json(ctx, f"{PROJECTS}/{pid}?token={token}")
    if not isinstance(project, dict) or "targets" not in project:
        raise WorkspaceError("This is not a Scratch 3 project (Scratch 2 / older projects can't be imported).")
    assets: dict[str, bytes] = {}
    for t in project["targets"]:
        for a in (t.get("costumes") or []) + (t.get("sounds") or []):
            fn = a.get("md5ext") or f"{a['assetId']}.{a['dataFormat']}"
            a["md5ext"] = fn
            if fn not in assets:
                assets[fn] = ctx.library.fetch(ASSET_URL.format(md5ext=fn))
    r = validate_project(project, set(assets))
    if not r.ok:
        raise WorkspaceError("The downloaded project failed validation:\n" + r.format())
    s = ctx.store.create(name or f"scratch-{pid}", project, assets)
    return {"imported": s.name, "title": meta.get("title"), "author": (meta.get("author") or {}).get("username"),
            "sprites": [t["name"] for t in project["targets"] if not t.get("isStage")], "asset_files": len(assets),
            "note": "Remember to credit the original author if you share a remix."}
