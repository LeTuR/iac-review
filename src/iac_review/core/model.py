"""The normalized vocabulary every adapter and provider speaks.

These types are the contract between a forge adapter (which knows about pull
requests and merge requests) and a provider module (which knows about a cloud).
Neither concern may leak in here: no forge identifiers with behaviour attached,
no cloud resource semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

FileStatus = Literal["added", "modified", "removed", "renamed"]
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """One file as it looks after the change, plus which lines the change touched."""

    path: str
    status: FileStatus
    content: str | None = None
    """Post-change file content. ``None`` when removed, or when the forge did not supply it."""
    changed_lines: frozenset[int] = frozenset()
    """1-based line numbers in the post-change file that the diff added or modified."""

    def touches(self, line: int | None) -> bool:
        """Whether ``line`` is part of this change (unknown lines count as touched)."""
        if line is None or not self.changed_lines:
            return True
        return line in self.changed_lines


@dataclass(frozen=True, slots=True)
class Changeset:
    """A pull request, merge request, or local branch, flattened to what review needs."""

    ref: str
    """Opaque identifier the originating adapter can round-trip (e.g. a PR number)."""
    title: str = ""
    base: str = ""
    head: str = ""
    origin: str = "unknown"
    """Name of the adapter that produced this changeset. Informational only."""
    files: tuple[ChangedFile, ...] = ()

    def by_suffix(self, *suffixes: str) -> tuple[ChangedFile, ...]:
        return tuple(f for f in self.files if f.status != "removed" and f.path.endswith(suffixes))


@dataclass(frozen=True, slots=True)
class Finding:
    """One reviewable remark, addressable back to a line of the change."""

    rule: str
    severity: Severity
    title: str
    detail: str
    path: str | None = None
    line: int | None = None
    suggestion: str | None = None
    references: tuple[str, ...] = ()

    def render(self) -> str:
        """Markdown body, forge-independent. Adapters decide where to put it."""
        parts = [f"**{self.title}**", "", self.detail]
        if self.suggestion:
            parts += ["", "```hcl", self.suggestion.rstrip(), "```"]
        if self.references:
            parts += ["", *(f"- {url}" for url in self.references)]
        parts += ["", f"<sub>`iac-review` · rule `{self.rule}` · {self.severity}</sub>"]
        return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class Node:
    """A box in the diagram. ``icon`` is resolved by the provider, drawn by the core."""

    id: str
    label: str
    kind: str
    icon: str | None = None
    group: str | None = None


@dataclass(frozen=True, slots=True)
class Edge:
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class Diagram:
    title: str = "Infrastructure"
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Something the run could not do. Never silently dropped, never fatal."""

    source: str
    message: str


@dataclass(frozen=True, slots=True)
class ProviderResult:
    findings: tuple[Finding, ...] = ()
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewResult:
    changeset: Changeset
    findings: tuple[Finding, ...] = ()
    diagram: Diagram = field(default_factory=Diagram)
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def worst(self) -> Severity | None:
        levels: tuple[Severity, ...] = ("error", "warning", "info")
        for level in levels:
            if any(f.severity == level for f in self.findings):
                return level
        return None


@runtime_checkable
class Provider(Protocol):
    """A cloud module. Owns every rule and icon decision for its own cloud."""

    name: str

    def analyze(self, changeset: Changeset) -> ProviderResult:
        """Review a changeset and contribute diagram nodes for it."""


@runtime_checkable
class Forge(Protocol):
    """A code-hosting adapter. Owns every PR/MR detail; the core sees none of it."""

    name: str

    def fetch(self, target: str) -> Changeset:
        """Turn a forge-native target (PR/MR reference) into a normalized changeset."""

    def publish(self, result: ReviewResult) -> None:
        """Post normalized findings back as review comments."""
