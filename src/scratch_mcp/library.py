"""Scratch's built-in library (sprites, costumes, backdrops, sounds).

Metadata comes from the scratch-gui repository; the asset files from Scratch's public asset CDN. Both are
fetched on demand and cached on disk. Network access is needed the first time; everything is read-only.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .workspace import WorkspaceError

KINDS = ("sprites", "costumes", "backdrops", "sounds")
META_URL = "https://raw.githubusercontent.com/scratchfoundation/scratch-gui/develop/src/lib/libraries/{kind}.json"
ASSET_URL = "https://cdn.assets.scratch.mit.edu/internalapi/asset/{md5ext}/get/"

Fetcher = Callable[[str], bytes]


def cache_dir() -> Path:
    base = os.environ.get("SCRATCH_MCP_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "scratch-mcp")
    p = Path(base) / "library"
    p.mkdir(parents=True, exist_ok=True)
    return p


def http_get(url: str, timeout: float = 25) -> bytes:
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        ctx = ssl.create_default_context(cafile=bundle)
    req = urllib.request.Request(url, headers={"User-Agent": "scratch-mcp"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:  # honours HTTPS_PROXY
            return r.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WorkspaceError(f"Could not download {url}: {exc}. The Scratch library needs internet access.") from exc


class Library:
    def __init__(self, fetch: Fetcher | None = None):
        self.fetch = fetch or http_get
        self._meta: dict[str, list[dict]] = {}

    def meta(self, kind: str) -> list[dict]:
        if kind not in KINDS:
            raise WorkspaceError(f"kind must be one of {', '.join(KINDS)}.")
        if kind not in self._meta:
            cached = cache_dir() / f"{kind}.json"
            if cached.exists():
                data = cached.read_bytes()
            else:
                data = self.fetch(META_URL.format(kind=kind))
                cached.write_bytes(data)
            self._meta[kind] = json.loads(data.decode("utf-8"))
        return self._meta[kind]

    def search(self, kind: str, query: str | None = None, tag: str | None = None, limit: int = 40) -> list[dict]:
        out = []
        for item in self.meta(kind):
            name = str(item.get("name", ""))
            tags = [str(t) for t in item.get("tags") or []]
            if query and query.lower() not in name.lower() and not any(query.lower() in t.lower() for t in tags):
                continue
            if tag and tag.lower() not in [t.lower() for t in tags]:
                continue
            out.append({"name": name, "tags": tags, **({"seconds": round(item["sampleCount"] / item["rate"], 2)} if item.get("rate") else {}),
                        **({"costumes": len(item.get("costumes") or [])} if kind == "sprites" else {})})
            if len(out) >= limit:
                break
        return out

    def find(self, kind: str, name: str) -> dict:
        items = self.meta(kind)
        for item in items:
            if item.get("name") == name:
                return item
        for item in items:
            if str(item.get("name", "")).lower() == name.lower():
                return item
        near = [str(i["name"]) for i in items if name.lower() in str(i["name"]).lower()][:8]
        raise WorkspaceError(f"No library {kind[:-1]} named '{name}'." + (f" Similar: {', '.join(near)}" if near else ""))

    def asset(self, md5ext: str) -> bytes:
        path = cache_dir() / md5ext
        if path.exists():
            return path.read_bytes()
        data = self.fetch(ASSET_URL.format(md5ext=md5ext))
        path.write_bytes(data)
        return data
