"""Read the Terraform in a changeset.

``python-hcl2`` gives the block structure; a line scan of the same source gives
the block header positions, so findings can be posted on the line a reader
actually sees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import hcl2
from hcl2.utils import SerializationOptions

from iac_review.core.model import ChangedFile, Diagnostic

_OPTIONS = SerializationOptions(strip_string_quotes=True)
_HEADER = re.compile(r'^\s*(resource|module|data)\s+"([^"]+)"(?:\s+"([^"]+)")?\s*\{')


@dataclass(frozen=True, slots=True)
class Block:
    """One ``resource``, ``data`` or ``module`` block."""

    kind: str
    type: str
    """Resource type for ``resource``/``data``; module source for ``module``."""
    name: str
    path: str
    line: int
    attributes: dict[str, Any]

    @property
    def address(self) -> str:
        prefix = {"resource": "", "data": "data.", "module": "module."}[self.kind]
        if self.kind == "module":
            return f"module.{self.name}"
        return f"{prefix}{self.type}.{self.name}"


def _header_lines(source: str) -> dict[tuple[str, str, str], list[int]]:
    found: dict[tuple[str, str, str], list[int]] = {}
    for number, text in enumerate(source.splitlines(), start=1):
        match = _HEADER.match(text)
        if match:
            kind, first, second = match.group(1), match.group(2), match.group(3) or ""
            found.setdefault((kind, first, second), []).append(number)
    return found


def parse(file: ChangedFile) -> tuple[list[Block], list[Diagnostic]]:
    """Parse one Terraform file into blocks, reporting parse failures as diagnostics."""
    if not file.content:
        return [], []
    try:
        document = hcl2.loads(file.content, serialization_options=_OPTIONS)
    except Exception as exc:
        return [], [Diagnostic("azure/terraform", f"{file.path}: could not parse ({exc})")]

    lines = _header_lines(file.content)
    blocks: list[Block] = []

    def take_line(key: tuple[str, str, str]) -> int:
        pending = lines.get(key)
        return pending.pop(0) if pending else 0

    for kind in ("resource", "data"):
        for entry in document.get(kind, []):
            for type_name, named in entry.items():
                for name, body in named.items():
                    blocks.append(
                        Block(
                            kind=kind,
                            type=type_name,
                            name=name,
                            path=file.path,
                            line=take_line((kind, type_name, name)),
                            attributes=dict(body),
                        )
                    )

    for entry in document.get("module", []):
        for name, body in entry.items():
            blocks.append(
                Block(
                    kind="module",
                    type=str(body.get("source", "")),
                    name=name,
                    path=file.path,
                    line=take_line(("module", name, "")),
                    attributes=dict(body),
                )
            )

    return blocks, []


def arguments(block: Block) -> set[str]:
    """Top-level argument and nested-block names declared on ``block``."""
    return {key for key in block.attributes if not key.startswith("__")}
