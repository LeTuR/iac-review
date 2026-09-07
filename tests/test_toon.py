"""The encoder against the rules it cites, https://github.com/toon-format/spec."""

from __future__ import annotations

import pytest

from iac_review.core import toon


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("has internal spaces", "has internal spaces"),
        ("", '""'),
        (" padded ", '" padded "'),
        ("true", '"true"'),
        ("null", '"null"'),
        ("42", '"42"'),
        ("-3.14", '"-3.14"'),
        ("1e-6", '"1e-6"'),
        ("main.tf:10", '"main.tf:10"'),
        ("a,b", '"a,b"'),
        ("array[0]", '"array[0]"'),
        ("-leading-hyphen", '"-leading-hyphen"'),
        ("#comment", '"#comment"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("two\nlines", '"two\\nlines"'),
        ("émoji 🚀 fine", "émoji 🚀 fine"),
    ],
)
def test_quoting_follows_section_7(raw: str, expected: str) -> None:
    assert toon.value(raw) == expected


def test_primitives_are_not_strings() -> None:
    assert toon.value(True) == "true"
    assert toon.value(False) == "false"
    assert toon.value(None) == "null"
    assert toon.value(7) == "7"


def test_tabular_array_header_and_rows() -> None:
    lines = toon.table(
        "findings",
        ("severity", "rule"),
        [{"severity": "warning", "rule": "azure/avm"}, {"severity": "error", "rule": "azure/x"}],
    )
    assert lines[0] == "findings[2]{severity,rule}:"
    assert lines[1] == "  warning,azure/avm"
    assert lines[2] == "  error,azure/x"


def test_inline_primitive_array() -> None:
    assert toon.array("help", ["do a thing", "do another"]) == ["help[2]: do a thing,do another"]


def test_empty_collections_use_the_bracket_form() -> None:
    assert toon.array("help", []) == ["help: []"]
    assert toon.table("notes", ("a",), []) == ["notes: []"]


def test_object_block_indents_its_fields() -> None:
    assert toon.block("review", {"files": 3, "origin": "local"}) == [
        "review:",
        "  files: 3",
        "  origin: local",
    ]


def test_document_ends_with_exactly_one_newline() -> None:
    rendered = toon.document([toon.field("a", "b")])
    assert rendered == "a: b\n"
    assert toon.document() == ""
