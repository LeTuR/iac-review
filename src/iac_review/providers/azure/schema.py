"""The AzureRM provider schema, and the rule that validates against it.

``terraform providers schema -json`` is the authoritative, machine-readable
answer to "will this actually apply": every resource, argument, type and
requiredness, for the provider version the repository pins. It is produced
locally and cached; it is never vendored, because it changes with every provider
release.

When Terraform is not on ``PATH`` the schema-backed rules report themselves as
skipped. A missing optional input degrades the review; it does not fail it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iac_review.core.cache import Cache
from iac_review.core.model import Diagnostic, Finding
from iac_review.providers.azure.terraform import Block, arguments

RULE = "azure/unknown-argument"
CACHE_KEY = "azure/azurerm-provider-schema.json"
PROVIDER_ADDRESS = "registry.terraform.io/hashicorp/azurerm"

BOOTSTRAP = """terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}
"""

_META_ARGUMENTS = frozenset(
    {
        "count",
        "for_each",
        "provider",
        "depends_on",
        "lifecycle",
        "provisioner",
        "connection",
        "dynamic",
    }
)


@dataclass(frozen=True, slots=True)
class ResourceSchema:
    type: str
    arguments: frozenset[str]
    required: frozenset[str]


class ProviderSchema:
    """Resource schemas for the AzureRM provider, as Terraform reports them."""

    def __init__(self, resources: dict[str, ResourceSchema], version: str | None = None) -> None:
        self._resources = resources
        self.version = version

    def __len__(self) -> int:
        return len(self._resources)

    def get(self, resource_type: str) -> ResourceSchema | None:
        return self._resources.get(resource_type)

    @classmethod
    def parse(cls, document: dict[str, Any]) -> ProviderSchema:
        schemas = document.get("provider_schemas") or {}
        provider = schemas.get(PROVIDER_ADDRESS)
        if provider is None:
            provider = next(
                (value for key, value in schemas.items() if key.endswith("/azurerm")), None
            )
        if provider is None:
            return cls({})
        resources: dict[str, ResourceSchema] = {}
        for resource_type, entry in (provider.get("resource_schemas") or {}).items():
            block = entry.get("block") or {}
            attributes = block.get("attributes") or {}
            block_types = block.get("block_types") or {}
            required = {
                name
                for name, spec in attributes.items()
                if spec.get("required") and not spec.get("computed")
            }
            resources[resource_type] = ResourceSchema(
                type=resource_type,
                arguments=frozenset(attributes) | frozenset(block_types),
                required=frozenset(required),
            )
        version = str((provider.get("provider") or {}).get("version") or "") or None
        return cls(resources, version=version)

    @classmethod
    def load(cls, cache: Cache) -> ProviderSchema | None:
        """Load the cached schema, or ``None`` when it has not been generated yet."""
        path = cache.root / CACHE_KEY
        if not path.exists():
            return None
        try:
            return cls.parse(json.loads(path.read_text()))
        except ValueError:
            return None


def terraform_binary() -> str | None:
    """Path to ``terraform`` or ``tofu``, whichever is installed."""
    return shutil.which("terraform") or shutil.which("tofu")


def generate(cache: Cache, *, binary: str | None = None, timeout: int = 900) -> Path:
    """Run Terraform to produce the provider schema and cache the result.

    Raises ``RuntimeError`` when Terraform is unavailable or the run fails.
    """
    executable = binary or terraform_binary()
    if executable is None:
        raise RuntimeError("terraform (or tofu) is not on PATH")
    with tempfile.TemporaryDirectory(prefix="iac-review-schema-") as workdir:
        (Path(workdir) / "providers.tf").write_text(BOOTSTRAP)
        for command in (
            [executable, "init", "-backend=false", "-input=false", "-no-color"],
            [executable, "providers", "schema", "-json"],
        ):
            completed = subprocess.run(
                command, cwd=workdir, capture_output=True, text=True, timeout=timeout, check=False
            )
            if completed.returncode != 0:
                raise RuntimeError(f"{' '.join(command)} failed: {completed.stderr.strip()}")
        target = cache.root / CACHE_KEY
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(completed.stdout)
        return target


def review_block(schema: ProviderSchema, block: Block) -> list[Finding]:
    """Flag arguments the provider does not accept for this resource type."""
    if block.kind != "resource":
        return []
    resource = schema.get(block.type)
    if resource is None:
        return []
    unknown = sorted(arguments(block) - resource.arguments - _META_ARGUMENTS)
    return [
        Finding(
            rule=RULE,
            severity="error",
            title=f"`{name}` is not an argument of `{block.type}`",
            detail=(
                f"The AzureRM provider schema for `{block.type}` does not define "
                f"`{name}`, so `terraform plan` will reject this configuration."
            ),
            path=block.path,
            line=block.line or None,
            references=(
                f"https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/{block.type.removeprefix('azurerm_')}",
            ),
        )
        for name in unknown
    ]


def unavailable() -> Diagnostic:
    return Diagnostic(
        "azure/schema",
        "AzureRM provider schema is not cached, so schema rules were skipped - "
        "run `iac-review cache refresh --schema` with terraform on PATH",
    )
