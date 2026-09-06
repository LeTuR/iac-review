from __future__ import annotations

from iac_review.core.model import ChangedFile, Changeset, Finding


def test_unknown_lines_count_as_touched() -> None:
    file = ChangedFile("main.tf", "modified")
    assert file.touches(12)
    assert file.touches(None)


def test_known_lines_are_respected() -> None:
    file = ChangedFile("main.tf", "modified", changed_lines=frozenset({4, 5}))
    assert file.touches(4)
    assert not file.touches(9)


def test_removed_files_are_not_reviewed() -> None:
    changeset = Changeset(
        ref="x",
        files=(ChangedFile("a.tf", "removed"), ChangedFile("b.tf", "added", content="")),
    )
    assert [f.path for f in changeset.by_suffix(".tf")] == ["b.tf"]


def test_rendered_finding_carries_rule_and_suggestion() -> None:
    body = Finding("r/x", "warning", "Title", "Detail", suggestion='module "a" {}').render()
    assert "Title" in body and "```hcl" in body and "`r/x`" in body
