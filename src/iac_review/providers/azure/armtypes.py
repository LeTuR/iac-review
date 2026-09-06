"""Resolve a Terraform resource type to its ARM resource type.

This is the join key between Terraform source and everything Azure publishes by
ARM type - the AVM module index first of all. The map comes from ``aztft``, the
library behind Microsoft's ``Azure/aztfexport``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from iac_review.core.cache import Cache
from iac_review.providers.azure import sources

_SCOPE_SEGMENTS = frozenset({"subscriptions", "resourcegroups", "managementgroups", "tenants"})


@dataclass(frozen=True, slots=True)
class ArmType:
    namespace: str
    """e.g. ``Microsoft.Storage``."""
    path: tuple[str, ...]
    """Full type path, e.g. ``("storageAccounts", "blobServices", "containers")``."""

    @property
    def primary(self) -> str | None:
        """The type this resource *is*, or ``None`` when it is a child or a link.

        Leading scope segments are not parents, so ``subscriptions/resourceGroups``
        is a primary ``resourceGroups``. A genuine child such as
        ``storageAccounts/blobServices/containers`` has no primary type: the module
        that owns it is the parent's, not its own.
        """
        remaining = list(self.path)
        while len(remaining) > 1 and remaining[0].lower() in _SCOPE_SEGMENTS:
            remaining.pop(0)
        return remaining[0] if len(remaining) == 1 else None

    @property
    def full(self) -> str:
        return f"{self.namespace}/{'/'.join(self.path)}"

    @property
    def key(self) -> str | None:
        """Lower-cased ``namespace/primary``, the AVM index join key."""
        primary = self.primary
        return f"{self.namespace}/{primary}".lower() if primary else None


class ArmTypeMap:
    """Terraform resource type to :class:`ArmType`."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    @classmethod
    def load(cls, cache: Cache, *, refresh: bool = False) -> ArmTypeMap:
        entry = cache.fetch(sources.ARM_TYPE_MAP, refresh=refresh)
        return cls(json.loads(entry.data))

    def get(self, terraform_type: str) -> ArmType | None:
        plane = (self._raw.get(terraform_type) or {}).get("management_plane")
        if not plane:
            return None
        namespace = plane.get("provider")
        path = tuple(plane.get("types") or ())
        if not namespace or not path:
            return None
        return ArmType(namespace=str(namespace), path=path)
