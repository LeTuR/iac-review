"""Resolve an Azure resource to a drawio shape.

The mapping is data, not code: :mod:`iac_review.providers.azure.data.icons` ships a
JSON file that can be replaced wholesale with ``IAC_REVIEW_AZURE_ICONS``. drawio's
Azure library is, in the captain's words, "usually not fully up to date", so an
unmapped type must degrade to a labelled generic shape and be reported - never
dropped, never fatal.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from iac_review.core.cache import Cache, Source

_PACKAGE = "iac_review.providers.azure.data"
_FILE = "icons.json"


@dataclass(frozen=True, slots=True)
class IconMap:
    prefix: str
    by_arm_type: dict[str, str]
    by_terraform_type: dict[str, str]

    @classmethod
    def load(cls, path: Path | None = None) -> IconMap:
        override = path or (
            Path(os.environ["IAC_REVIEW_AZURE_ICONS"])
            if os.environ.get("IAC_REVIEW_AZURE_ICONS")
            else None
        )
        if override is not None:
            raw: dict[str, Any] = json.loads(override.read_text())
        else:
            raw = json.loads(resources.files(_PACKAGE).joinpath(_FILE).read_text())
        return cls(
            prefix=str(raw.get("prefix", "")),
            by_arm_type={k.lower(): v for k, v in (raw.get("by_arm_type") or {}).items()},
            by_terraform_type={
                k.lower(): v for k, v in (raw.get("by_terraform_type") or {}).items()
            },
        )

    def resolve(self, terraform_type: str, arm_type_key: str | None) -> str | None:
        """Return a drawio ``image=`` value, or ``None`` when nothing is mapped."""
        shape = self.by_terraform_type.get(terraform_type.lower())
        if shape is None and arm_type_key:
            shape = self.by_arm_type.get(arm_type_key.lower())
        return f"{self.prefix}{shape}" if shape else None

    @property
    def shapes(self) -> set[str]:
        return set(self.by_arm_type.values()) | set(self.by_terraform_type.values())


class DrawioIconSource:
    """Fetches drawio's Azure shape files so they can be embedded in an SVG.

    A ``.drawio`` file only needs the relative path, which drawio resolves
    itself. A standalone image needs the bytes, so they are fetched from the
    library drawio publishes and cached like every other upstream source.
    Offline, or for a shape that has been renamed, this returns ``None`` and the
    node degrades to a labelled generic box.
    """

    RAW_ROOT = "https://raw.githubusercontent.com/jgraph/drawio/dev/src/main/webapp/"

    def __init__(self, cache: Cache) -> None:
        self._cache = cache
        self._memo: dict[str, bytes | None] = {}

    def read(self, reference: str) -> bytes | None:
        if reference not in self._memo:
            self._memo[reference] = self._fetch(reference)
        return self._memo[reference]

    def _fetch(self, reference: str) -> bytes | None:
        if not reference.startswith("img/lib/") or ".." in reference:
            return None
        source = Source(
            key=f"azure/shapes/{reference.removeprefix('img/lib/')}",
            url=self.RAW_ROOT + reference,
            description=f"drawio shape {reference}",
            ttl=30 * 24 * 3600,
        )
        try:
            return self._cache.fetch(source).data
        except (OSError, ValueError):
            return None
