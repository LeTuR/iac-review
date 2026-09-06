"""Unified-diff parsing.

Every forge hands out unified diffs, so this stays in the core: it is a patch
format, not a forge feature.
"""

from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def changed_lines(patch: str) -> frozenset[int]:
    """1-based line numbers in the post-change file that ``patch`` adds or modifies.

    An empty result means "unknown", which callers treat as "the whole file is in
    scope" rather than "nothing changed".
    """
    touched: set[int] = set()
    cursor = 0
    for raw in patch.splitlines():
        hunk = _HUNK.match(raw)
        if hunk:
            cursor = int(hunk.group(1))
            continue
        if cursor == 0 or raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            touched.add(cursor)
            cursor += 1
        elif raw.startswith("-"):
            continue
        else:
            cursor += 1
    return frozenset(touched)
