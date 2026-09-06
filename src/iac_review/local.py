"""Build a changeset from files on disk.

Not a forge: there is no pull request here, and nothing to post back. This is how
the reviewer runs against a working tree or a fixture, which is also how the
committed example diagram is produced.
"""

from __future__ import annotations

from pathlib import Path

from iac_review.core.model import ChangedFile, Changeset


def changeset_from_path(root: Path, *, pattern: str = "*.tf") -> Changeset:
    """Treat every matching file under ``root`` as fully in scope."""
    files = [
        ChangedFile(
            path=str(path.relative_to(root)),
            status="modified",
            content=path.read_text(encoding="utf-8", errors="replace"),
        )
        for path in sorted(root.rglob(pattern))
        if path.is_file()
    ]
    return Changeset(ref=str(root), title=root.name, origin="local", files=tuple(files))
