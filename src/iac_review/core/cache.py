"""A refreshable on-disk cache for the upstream data this review depends on.

AVM's module index, the Terraform-to-ARM type map and drawio's icon catalogue all
move independently of this repository, so none of them is vendored. They are
fetched on demand, cached under ``$XDG_CACHE_HOME/iac-review`` and refreshed with
``iac-review cache refresh``.

Offline is a first-class case: a stale cache is used with a diagnostic rather
than failing the review.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

USER_AGENT = "iac-review (+https://github.com/LeTuR/iac-review)"
DEFAULT_TTL = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class Source:
    """An upstream artefact worth caching."""

    key: str
    url: str
    description: str
    ttl: int = DEFAULT_TTL


@dataclass(frozen=True, slots=True)
class Entry:
    data: bytes
    path: Path
    fetched_at: float
    stale: bool = False
    note: str | None = None


def default_root() -> Path:
    override = os.environ.get("IAC_REVIEW_CACHE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "iac-review"


class Cache:
    """Fetch-once, refresh-on-demand storage for :class:`Source` artefacts."""

    def __init__(self, root: Path | None = None, *, offline: bool = False) -> None:
        self.root = root or default_root()
        self.offline = offline

    def path(self, source: Source) -> Path:
        return self.root / source.key

    def _meta_path(self, source: Source) -> Path:
        return self.root / f"{source.key}.meta.json"

    def meta(self, source: Source) -> dict[str, Any]:
        try:
            loaded = json.loads(self._meta_path(source).read_text())
        except (OSError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def fetch(self, source: Source, *, refresh: bool = False) -> Entry:
        """Return ``source``'s bytes, downloading them when missing, stale or forced."""
        path = self.path(source)
        cached = path.read_bytes() if path.exists() else None
        fetched_at = float(self.meta(source).get("fetched_at", 0) or 0)
        fresh_enough = cached is not None and (time.time() - fetched_at) < source.ttl

        if cached is not None and fresh_enough and not refresh:
            return Entry(cached, path, fetched_at)
        if self.offline:
            if cached is None:
                raise FileNotFoundError(f"{source.key} is not cached and offline mode is on")
            return Entry(cached, path, fetched_at, stale=True, note="offline: using cached copy")

        try:
            data = self._download(source.url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if cached is None:
                raise
            return Entry(cached, path, fetched_at, stale=True, note=f"refresh failed ({exc})")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        now = time.time()
        self._meta_path(source).write_text(
            json.dumps(
                {
                    "url": source.url,
                    "description": source.description,
                    "fetched_at": now,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                },
                indent=2,
            )
            + "\n"
        )
        return Entry(data, path, now)

    @staticmethod
    def _download(url: str, timeout: int = 30) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return bytes(response.read())
