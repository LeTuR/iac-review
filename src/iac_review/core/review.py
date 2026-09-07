"""Run every configured provider over a changeset and merge the results."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from iac_review.core.model import (
    Changeset,
    Diagram,
    Edge,
    Finding,
    IconSource,
    Node,
    Provider,
    ReviewResult,
)


class _CombinedIcons:
    """Asks each provider's icon source in turn."""

    def __init__(self, sources: Sequence[IconSource]) -> None:
        self._sources = tuple(sources)

    def read(self, reference: str) -> bytes | None:
        for source in self._sources:
            found = source.read(reference)
            if found is not None:
                return found
        return None


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def review(changeset: Changeset, providers: Iterable[Provider]) -> ReviewResult:
    """Review ``changeset`` with ``providers`` and return one normalized result.

    A provider that raises is reported as a diagnostic; one broken provider must
    not lose the findings of the others.
    """
    findings: list[Finding] = []
    nodes: list[Node] = []
    edges: list[Edge] = []
    diagnostics = []
    icon_sources: list[IconSource] = []

    for provider in providers:
        try:
            result = provider.analyze(changeset)
        except Exception as exc:
            from iac_review.core.model import Diagnostic

            diagnostics.append(Diagnostic(provider.name, f"provider failed: {exc!r}"))
            continue
        findings.extend(result.findings)
        nodes.extend(result.nodes)
        edges.extend(result.edges)
        diagnostics.extend(result.diagnostics)
        if result.icons is not None:
            icon_sources.append(result.icons)

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.path or "", f.line or 0))
    known = {node.id for node in nodes}
    return ReviewResult(
        changeset=changeset,
        findings=tuple(findings),
        diagram=Diagram(
            title=changeset.title or "Infrastructure",
            nodes=tuple(nodes),
            edges=tuple(e for e in edges if e.source in known and e.target in known),
        ),
        diagnostics=tuple(diagnostics),
        icons=_CombinedIcons(icon_sources) if icon_sources else None,
    )
