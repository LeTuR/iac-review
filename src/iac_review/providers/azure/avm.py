"""Azure Verified Modules: the index, and the rule that uses it.

The captain's standing rule is AVM over hand-rolled resources on Azure, so
"there is a published module for this" is the highest-value remark this reviewer
can make. The index is a CSV that AVM itself publishes and keeps current; the
recommended pin comes from the Terraform Registry, which is where the version
actually lives.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from iac_review.core.cache import Cache, Source
from iac_review.core.model import Diagnostic, Finding
from iac_review.providers.azure import sources
from iac_review.providers.azure.armtypes import ArmType
from iac_review.providers.azure.terraform import Block

RULE = "azure/avm-module-available"
REGISTRY_NAMESPACE = "Azure"


@dataclass(frozen=True, slots=True)
class Module:
    name: str
    display_name: str
    status: str
    namespace: str
    resource_type: str
    repo_url: str
    registry_url: str

    @property
    def registry_source(self) -> str:
        """The ``source`` string a Terraform ``module`` block would use."""
        return f"{REGISTRY_NAMESPACE}/{self.name}/azurerm"


class AvmIndex:
    """AVM's published Terraform resource-module index, keyed by ARM type."""

    def __init__(self, modules: dict[str, Module]) -> None:
        self._modules = modules

    @classmethod
    def load(cls, cache: Cache, *, refresh: bool = False) -> AvmIndex:
        entry = cache.fetch(sources.AVM_INDEX, refresh=refresh)
        text = entry.data.decode("utf-8-sig")
        modules: dict[str, Module] = {}
        for row in csv.DictReader(io.StringIO(text)):
            namespace = (row.get("ProviderNamespace") or "").strip()
            resource_type = (row.get("ResourceType") or "").strip()
            if not namespace or not resource_type:
                continue
            modules[f"{namespace}/{resource_type}".lower()] = Module(
                name=(row.get("ModuleName") or "").strip(),
                display_name=(row.get("ModuleDisplayName") or "").strip(),
                status=(row.get("ModuleStatus") or "").strip(),
                namespace=namespace,
                resource_type=resource_type,
                repo_url=(row.get("RepoURL") or "").strip(),
                registry_url=(row.get("PublicRegistryReference") or "").strip(),
            )
        return cls(modules)

    def available_for(self, arm_type: ArmType) -> Module | None:
        """The published module that owns ``arm_type``, if one exists today.

        Only ``Available`` modules are returned. Recommending a ``Proposed``
        module would send a reviewer to a registry entry that does not exist yet.
        """
        key = arm_type.key
        if not key:
            return None
        module = self._modules.get(key)
        return module if module and module.status == "Available" else None


def latest_version(cache: Cache, module: Module, *, refresh: bool = False) -> str | None:
    """Latest published version of ``module`` from the Terraform Registry."""
    source = Source(
        key=f"azure/registry/{module.name}.json",
        url=(
            f"https://registry.terraform.io/v1/modules/{REGISTRY_NAMESPACE}/{module.name}/azurerm"
        ),
        description=f"Terraform Registry metadata for {module.name}",
        ttl=24 * 3600,
    )
    try:
        entry = cache.fetch(source, refresh=refresh)
        version = json.loads(entry.data).get("version")
    except (OSError, ValueError):
        return None
    return str(version) if version else None


def _suggestion(block: Block, module: Module, version: str | None) -> str:
    pin = f'\n  version = "{version}"' if version else ""
    return (
        f'module "{block.name}" {{\n'
        f'  source  = "{module.registry_source}"{pin}\n'
        f"  # ... module inputs replace the {block.type} arguments\n"
        f"}}"
    )


def review_block(
    cache: Cache, index: AvmIndex, block: Block, arm_type: ArmType | None
) -> Finding | None:
    """Flag a hand-rolled resource that an published AVM module already covers."""
    if block.kind != "resource" or arm_type is None:
        return None
    module = index.available_for(arm_type)
    if module is None:
        return None
    version = latest_version(cache, module)
    return Finding(
        rule=RULE,
        severity="warning",
        title=f"Use the AVM module for {module.display_name or module.resource_type}",
        detail=(
            f"`{block.address}` hand-rolls `{arm_type.full}`. Azure Verified Modules "
            f"publishes `{module.name}` for this resource type, and it is marked "
            f"**{module.status}**. AVM modules carry the WAF-aligned defaults, "
            f"diagnostic settings, private endpoint and RBAC wiring that a bare "
            f"`{block.type}` resource does not."
        ),
        path=block.path,
        line=block.line or None,
        suggestion=_suggestion(block, module, version),
        references=tuple(url for url in (module.registry_url, module.repo_url) if url),
    )


def index_diagnostic(cache: Cache) -> Diagnostic | None:
    entry_meta = cache.meta(sources.AVM_INDEX)
    if not entry_meta:
        return Diagnostic("azure/avm", "AVM index has never been fetched")
    return None
