from __future__ import annotations

from typing import Any

import pytest

from iac_review import forges
from iac_review.core.model import ChangedFile, Changeset, Finding, ReviewResult
from iac_review.forges.github import GitHubForge, parse_target
from iac_review.forges.gitlab import GitLabForge


def test_both_forges_are_registered() -> None:
    assert forges.names() == ("github", "gitlab")


def test_unknown_forge_names_the_known_ones() -> None:
    with pytest.raises(KeyError, match="github"):
        forges.get("bitbucket")


@pytest.mark.parametrize(
    "target",
    ["LeTuR/iac-review#7", "https://github.com/LeTuR/iac-review/pull/7"],
)
def test_target_forms(target: str) -> None:
    pull = parse_target(target)
    assert (pull.owner, pull.repo, pull.number) == ("LeTuR", "iac-review", 7)


def test_bad_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a GitHub pull request"):
        parse_target("just-a-branch")


class _Recorder(GitHubForge):
    def __init__(self) -> None:
        super().__init__(auth="test-token")
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, path, payload))
        return {}


def _result() -> ReviewResult:
    changeset = Changeset(
        ref="LeTuR/iac-review#7",
        files=(ChangedFile("main.tf", "modified", changed_lines=frozenset({10})),),
    )
    return ReviewResult(
        changeset=changeset,
        findings=(
            Finding("azure/avm-module-available", "warning", "In diff", "d", "main.tf", 10),
            Finding("azure/avm-module-available", "warning", "Outside diff", "d", "main.tf", 99),
            Finding("azure/other", "info", "No location", "d"),
        ),
    )


def test_publish_puts_in_diff_findings_inline_and_the_rest_in_the_body() -> None:
    forge = _Recorder()
    forge.publish(_result())

    method, path, payload = forge.calls[-1]
    assert payload is not None
    assert method == "POST"
    assert path == "/repos/LeTuR/iac-review/pulls/7/reviews"
    assert payload["event"] == "COMMENT"
    assert [c["line"] for c in payload["comments"]] == [10]
    assert payload["comments"][0]["side"] == "RIGHT"
    assert "Outside diff" in payload["body"]
    assert "No location" in payload["body"]
    assert "2 warning" in payload["body"]


def test_gitlab_is_registered_but_states_what_it_needs() -> None:
    forge = forges.get("gitlab")
    assert isinstance(forge, GitLabForge)
    with pytest.raises(NotImplementedError, match=r"gitlab\.py"):
        forge.fetch("group/project!1")
