"""GitHub adapter: pull request in, review comments out.

Chosen as the first forge because every repository this reviewer is aimed at
today lives on GitHub, and its review API accepts a batch of line-anchored
comments in a single call, so one review posts atomically instead of a stream of
individual comments.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from iac_review.core.diff import changed_lines
from iac_review.core.model import ChangedFile, Changeset, FileStatus, ReviewResult

API_ROOT = os.environ.get("GITHUB_API_URL", "https://api.github.com")
_TARGET = re.compile(
    r"^(?:https?://[^/]+/)?(?P<owner>[^/\s]+)/(?P<repo>[^/\s#]+)(?:/pull/|#)(?P<number>\d+)/?$"
)
_STATUS: dict[str, FileStatus] = {
    "added": "added",
    "modified": "modified",
    "removed": "removed",
    "renamed": "renamed",
    "changed": "modified",
    "copied": "added",
}


@dataclass(frozen=True, slots=True)
class PullRequest:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_target(target: str) -> PullRequest:
    """Accept ``owner/repo#7`` or a ``https://github.com/owner/repo/pull/7`` URL."""
    match = _TARGET.match(target.strip())
    if not match:
        raise ValueError(f"not a GitHub pull request: {target!r} (expected owner/repo#123)")
    return PullRequest(match["owner"], match["repo"], int(match["number"]))


def token() -> str:
    """Resolve a GitHub token from the environment, falling back to the ``gh`` CLI."""
    for variable in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(variable)
        if value:
            return value
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise RuntimeError("no GitHub credentials: set GITHUB_TOKEN or run `gh auth login`")


class GitHubForge:
    """Reads pull requests and writes pull request reviews."""

    name = "github"

    RAW_ROOT = "https://raw.githubusercontent.com"

    def __init__(self, api_root: str = API_ROOT, auth: str | None = None) -> None:
        self._api_root = api_root.rstrip("/")
        self._auth = auth
        self._pull: PullRequest | None = None
        self._head_sha = ""

    def fetch(self, target: str) -> Changeset:
        pull = parse_target(target)
        self._pull = pull
        base = f"/repos/{pull.owner}/{pull.repo}/pulls/{pull.number}"
        details = self._request("GET", base)
        head_sha = str(details.get("head", {}).get("sha", ""))
        self._head_sha = head_sha

        files: list[ChangedFile] = []
        for entry in self._paged(f"{base}/files"):
            path = str(entry["filename"])
            status = _STATUS.get(str(entry.get("status")), "modified")
            patch = str(entry.get("patch") or "")
            files.append(
                ChangedFile(
                    path=path,
                    status=status,
                    content=None if status == "removed" else self._contents(pull, path, head_sha),
                    changed_lines=changed_lines(patch),
                )
            )

        return Changeset(
            ref=pull.slug,
            title=str(details.get("title") or pull.slug),
            base=str(details.get("base", {}).get("ref", "")),
            head=str(details.get("head", {}).get("ref", "")),
            origin=self.name,
            files=tuple(files),
        )

    def publish(self, result: ReviewResult) -> None:
        """Post one review: line findings inline, the rest in the review body."""
        if self._pull is None:
            self._pull = parse_target(result.changeset.ref)
        pull = self._pull
        in_diff = {
            file.path: file.changed_lines for file in result.changeset.files if file.changed_lines
        }

        comments: list[dict[str, Any]] = []
        summary: list[str] = []
        for finding in result.findings:
            lines = in_diff.get(finding.path or "")
            if finding.path and finding.line and lines and finding.line in lines:
                comments.append(
                    {
                        "path": finding.path,
                        "line": finding.line,
                        "side": "RIGHT",
                        "body": finding.render(),
                    }
                )
            else:
                summary.append(finding.render())

        body = _body(result, summary, self._diagram_markdown(pull, result))
        self._request(
            "POST",
            f"/repos/{pull.owner}/{pull.repo}/pulls/{pull.number}/reviews",
            {"body": body, "event": "COMMENT", "comments": comments},
        )

    def _diagram_markdown(self, pull: PullRequest, result: ReviewResult) -> str:
        """Show the diagram if GitHub can reach it, and say so plainly if it cannot.

        GitHub publishes no API for attaching an image to a review comment - its
        own OpenAPI description carries no such endpoint - so a generated file
        cannot be uploaded. What does work is a raw URL to a file that exists in
        the repository at the head commit, which raw.githubusercontent serves as
        ``image/svg+xml``. So a diagram committed alongside the Terraform is
        displayed inline; one merely written to disk is named instead of being
        silently dropped.
        """
        path = result.diagram_path
        if not path:
            return ""
        if self._head_sha and self._contents(pull, path, self._head_sha) is not None:
            url = f"{self.RAW_ROOT}/{pull.owner}/{pull.repo}/{self._head_sha}/{path}"
            return (
                f'<img src="{url}" alt="Infrastructure diagram" width="100%">\n\n'
                f"<sub>Open [`{path}`]({url}) in drawio to edit - "
                f"the diagram source travels inside the image.</sub>"
            )
        return (
            f"The diagram was written to `{path}`, which is not committed at this "
            "commit, so it cannot be displayed here. Commit it to have it shown inline."
        )

    def _contents(self, pull: PullRequest, path: str, ref: str) -> str | None:
        url = (
            f"{self._api_root}/repos/{pull.owner}/{pull.repo}/contents/"
            f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}"
        )
        request = urllib.request.Request(
            url, headers={**self._headers(), "Accept": "application/vnd.github.raw+json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return bytes(response.read()).decode("utf-8", errors="replace")
        except (urllib.error.URLError, UnicodeError, OSError):
            return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._auth or token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "iac-review",
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self._api_root}{path}", data=data, method=method, headers=self._headers()
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"null")

    def _paged(self, path: str) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page = 1
        while page <= 30:
            batch = self._request("GET", f"{path}?per_page=100&page={page}")
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return collected


def _body(result: ReviewResult, summary: list[str], diagram: str = "") -> str:
    counts = {
        level: sum(1 for f in result.findings if f.severity == level)
        for level in ("error", "warning", "info")
    }
    counted = ", ".join(f"{count} {level}" for level, count in counts.items() if count)
    headline = counted or "no findings"
    parts = [f"### `iac-review`\n\n{headline}."]
    if diagram:
        parts.append(diagram)
    if summary:
        parts.append("\n\n---\n\n".join(summary))
    if result.diagnostics:
        notes = "\n".join(f"- `{d.source}` {d.message}" for d in result.diagnostics)
        parts.append(f"<details><summary>Diagnostics</summary>\n\n{notes}\n\n</details>")
    return "\n\n".join(parts)
