"""A TOON encoder for the shapes this CLI emits.

TOON (Token-Oriented Object Notation) is the output format AXI requires on
stdout. Only the forms used here are implemented - object blocks, tabular
arrays and inline primitive arrays - because a partial encoder that is correct
beats a general one that is nearly correct.

Rules implemented verbatim from the specification:
§7.1 escaping, §7.2 quoting, §8 objects, §9.1 inline primitive arrays,
§9.3 tabular arrays. https://github.com/toon-format/spec
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

INDENT = "  "
DELIMITER = ","

_NUMERIC_LIKE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)
_MUST_QUOTE_ANYWHERE = frozenset(':"\\[]{}' + DELIMITER)
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _needs_quotes(text: str) -> bool:
    """Per §7.2. Kept as a single predicate so the rules read in spec order."""
    if text == "":
        return True
    if text != text.strip(" \t"):
        return True
    if text in {"true", "false", "null"}:
        return True
    if _NUMERIC_LIKE.match(text):
        return True
    if any(character in _MUST_QUOTE_ANYWHERE for character in text):
        return True
    if any(character <= "\x1f" for character in text):
        return True
    return text.startswith(("-", "#"))


def _escape(text: str) -> str:
    out: list[str] = []
    for character in text:
        if character in _ESCAPES:
            out.append(_ESCAPES[character])
        elif character <= "\x1f":
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(character)
    return "".join(out)


def value(raw: Any) -> str:
    """Encode one primitive (§7)."""
    if raw is None:
        return "null"
    if raw is True:
        return "true"
    if raw is False:
        return "false"
    if isinstance(raw, int | float):
        return str(raw)
    text = str(raw)
    return f'"{_escape(text)}"' if _needs_quotes(text) else text


def field(key: str, raw: Any, depth: int = 0) -> str:
    return f"{INDENT * depth}{key}: {value(raw)}"


def block(name: str, fields: Mapping[str, Any], depth: int = 0) -> list[str]:
    """An object under a key (§8)."""
    lines = [f"{INDENT * depth}{name}:"]
    lines.extend(field(key, raw, depth + 1) for key, raw in fields.items())
    return lines


def array(name: str, values: Sequence[Any], depth: int = 0) -> list[str]:
    """An inline primitive array (§9.1). Empty arrays use the ``key: []`` form."""
    if not values:
        return [f"{INDENT * depth}{name}: []"]
    joined = DELIMITER.join(value(item) for item in values)
    return [f"{INDENT * depth}{name}[{len(values)}]: {joined}"]


def table(
    name: str, fields: Sequence[str], rows: Sequence[Mapping[str, Any]], depth: int = 0
) -> list[str]:
    """A tabular array of uniform objects (§9.3)."""
    if not rows:
        return [f"{INDENT * depth}{name}: []"]
    header = f"{INDENT * depth}{name}[{len(rows)}]{{{','.join(fields)}}}:"
    body = [
        INDENT * (depth + 1) + DELIMITER.join(value(row.get(key)) for key in fields) for row in rows
    ]
    return [header, *body]


def document(*sections: Iterable[str]) -> str:
    lines = [line for section in sections for line in section]
    return "\n".join(lines) + "\n" if lines else ""
