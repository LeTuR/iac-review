"""The Azure provider module.

Everything Azure-specific lives under here: how Terraform maps to ARM types,
which AVM module owns a resource type, which drawio shape draws it. The core
imports none of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from iac_review.core.cache import Cache
from iac_review.core.model import (
    ChangedFile,
    Changeset,
    Diagnostic,
    Edge,
    Finding,
    Node,
    ProviderResult,
)
from iac_review.providers.azure import avm, schema
from iac_review.providers.azure.armtypes import ArmType, ArmTypeMap
from iac_review.providers.azure.icons import IconMap
from iac_review.providers.azure.terraform import Block, parse

_REFERENCE = re.compile(r"\b(azurerm_[a-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_-]*)")
_RESOURCE_GROUP = "azurerm_resource_group"


def _node_id(address: str) -> str:
    return "n-" + re.sub(r"[^A-Za-z0-9_-]", "-", address)


def _references(block: Block) -> set[str]:
    """Addresses of other azurerm resources this block interpolates."""
    found: set[str] = set()
    for key, value in block.attributes.items():
        if key.startswith("__"):
            continue
        for resource_type, name in _REFERENCE.findall(repr(value)):
            found.add(f"{resource_type}.{name}")
    return found


class AzureProvider:
    """Reviews Terraform that targets Azure."""

    name = "azure"

    def __init__(self, cache: Cache | None = None, *, icons: IconMap | None = None) -> None:
        self._cache = cache or Cache()
        self._icons = icons or IconMap.load()

    def analyze(self, changeset: Changeset) -> ProviderResult:
        files = changeset.by_suffix(".tf")
        if not files:
            return ProviderResult()

        blocks: list[Block] = []
        diagnostics: list[Diagnostic] = []
        for file in files:
            parsed, problems = parse(file)
            blocks.extend(parsed)
            diagnostics.extend(problems)

        touched = {file.path: file for file in files}
        arm_map = ArmTypeMap.load(self._cache)
        arm_types = {block.address: arm_map.get(block.type) for block in blocks}

        findings, avm_notes = self._review(blocks, arm_types, touched)
        diagnostics.extend(avm_notes)

        nodes, edges, icon_notes = self._draw(blocks, arm_types)
        diagnostics.extend(icon_notes)

        return ProviderResult(
            findings=tuple(findings),
            nodes=tuple(nodes),
            edges=tuple(edges),
            diagnostics=tuple(diagnostics),
        )

    def _review(
        self,
        blocks: Iterable[Block],
        arm_types: dict[str, ArmType | None],
        touched: Mapping[str, ChangedFile],
    ) -> tuple[list[Finding], list[Diagnostic]]:
        index = avm.AvmIndex.load(self._cache)
        provider_schema = schema.ProviderSchema.load(self._cache)
        diagnostics: list[Diagnostic] = []
        if provider_schema is None:
            diagnostics.append(schema.unavailable())

        findings: list[Finding] = []
        for block in blocks:
            file = touched.get(block.path)
            if file is not None and not file.touches(block.line or None):
                continue
            finding = avm.review_block(self._cache, index, block, arm_types.get(block.address))
            if finding is not None:
                findings.append(finding)
            if provider_schema is not None:
                findings.extend(schema.review_block(provider_schema, block))
        return findings, diagnostics

    def _draw(
        self, blocks: Iterable[Block], arm_types: dict[str, ArmType | None]
    ) -> tuple[list[Node], list[Edge], list[Diagnostic]]:
        resources = [b for b in blocks if b.kind == "resource"]
        known = {b.address for b in resources}
        nodes: list[Node] = []
        edges: list[Edge] = []
        unmapped: set[str] = set()

        for block in resources:
            arm_type = arm_types.get(block.address)
            icon = self._icons.resolve(block.type, arm_type.key if arm_type else None)
            if icon is None:
                unmapped.add(block.type)
            references = _references(block)
            group = next(
                (ref for ref in sorted(references) if ref.startswith(f"{_RESOURCE_GROUP}.")),
                None,
            )
            nodes.append(
                Node(
                    id=_node_id(block.address),
                    label=block.name,
                    kind=block.type,
                    icon=icon,
                    group=group.split(".", 1)[1] if group else block.path,
                )
            )
            for reference in sorted(references):
                if reference in known and reference != block.address:
                    edges.append(Edge(_node_id(block.address), _node_id(reference)))

        diagnostics = [
            Diagnostic(
                "azure/icons",
                f"no Azure shape mapped for {resource_type} - drawn as a labelled generic "
                "shape; add it to the icon map to fix",
            )
            for resource_type in sorted(unmapped)
        ]
        return nodes, edges, diagnostics
