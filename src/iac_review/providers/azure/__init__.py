"""The Azure provider module.

Everything Azure-specific lives under here: how Terraform maps to ARM types,
which AVM module owns a resource type, which drawio shape draws it. The core
imports none of it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import replace

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
from iac_review.providers.azure.icons import DrawioIconSource, IconMap
from iac_review.providers.azure.terraform import Block, parse

_REFERENCE = re.compile(r"\b(azurerm_[a-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_-]*)")
_RESOURCE_GROUP = "azurerm_resource_group"


def _node_id(address: str) -> str:
    return "n-" + re.sub(r"[^A-Za-z0-9_-]", "-", address)


def _group_of(block: Block, references: set[str]) -> str:
    """Azure groups by resource group, so the diagram does too.

    A resource group heads its own box; anything referencing one joins it.
    Everything else falls back to the file it was declared in.
    """
    if block.type == _RESOURCE_GROUP:
        return block.name
    owner = next((ref for ref in sorted(references) if ref.startswith(f"{_RESOURCE_GROUP}.")), None)
    return owner.split(".", 1)[1] if owner else block.path


def _inherit_groups(nodes: list[Node], resources: list[Block]) -> list[Node]:
    """Pull a resource into the group of whatever it hangs off, transitively.

    A storage container names no resource group - its storage account does, and
    that account may itself only inherit its group from further up the chain.
    Declaration order in the file is irrelevant, so each resource walks its own
    reference chain to a settled owner rather than relying on a single pass over
    file order; a `visiting` set guards against a resource ever revisiting an
    address still being resolved, so a self- or mutually-referencing pair can't
    recurse forever.
    """
    node_by_id = {node.id: node for node in nodes}
    by_address = {block.address: block for block in resources}
    resolved: dict[str, str | None] = {}
    visiting: set[str] = set()

    def resolve(block: Block) -> str | None:
        node_id = _node_id(block.address)
        if node_id in resolved:
            return resolved[node_id]
        own_group = node_by_id[node_id].group
        if node_id in visiting:
            return own_group
        if own_group != block.path:
            resolved[node_id] = own_group
            return own_group
        visiting.add(node_id)
        best: str | None = own_group
        for reference in sorted(_references(block)):
            parent = by_address.get(reference)
            if parent is None or parent.address == block.address:
                continue
            inherited = resolve(parent)
            if inherited != parent.path:
                best = inherited
                break
        visiting.discard(node_id)
        resolved[node_id] = best
        return best

    for block in resources:
        resolve(block)

    return [
        node if node.group == resolved[node.id] else replace(node, group=resolved[node.id])
        for node in nodes
    ]


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
            icons=DrawioIconSource(self._cache),
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
            nodes.append(
                Node(
                    id=_node_id(block.address),
                    label=block.name,
                    kind=block.type,
                    icon=icon,
                    group=_group_of(block, references),
                )
            )
            for reference in sorted(references):
                if reference in known and reference != block.address:
                    edges.append(Edge(_node_id(block.address), _node_id(reference)))

        nodes = _inherit_groups(nodes, resources)

        diagnostics = [
            Diagnostic(
                "azure/icons",
                f"no Azure shape mapped for {resource_type} - drawn as a labelled generic "
                "shape; add it to the icon map to fix",
            )
            for resource_type in sorted(unmapped)
        ]
        return nodes, edges, diagnostics
