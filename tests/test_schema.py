from __future__ import annotations

import json
from pathlib import Path

from iac_review.core.model import ChangedFile
from iac_review.providers.azure.schema import ProviderSchema, review_block, terraform_binary
from iac_review.providers.azure.terraform import Block, parse

SCHEMA = ProviderSchema.parse(
    json.loads((Path(__file__).parent / "data" / "azurerm-provider-schema.json").read_text())
)


def _block(source: str) -> Block:
    blocks, _ = parse(ChangedFile("main.tf", "modified", content=source))
    return blocks[0]


def test_schema_reports_the_provider_version() -> None:
    assert SCHEMA.version == "4.0.0"
    assert len(SCHEMA) == 1


def test_unknown_argument_is_an_error() -> None:
    block = _block(
        'resource "azurerm_storage_account" "a" {\n'
        '  name          = "st"\n'
        "  bogus_setting = true\n"
        "}\n"
    )
    findings = review_block(SCHEMA, block)
    assert [f.title for f in findings] == [
        "`bogus_setting` is not an argument of `azurerm_storage_account`"
    ]
    assert findings[0].severity == "error"
    assert findings[0].line == 1


def test_nested_blocks_and_meta_arguments_are_accepted() -> None:
    block = _block(
        'resource "azurerm_storage_account" "a" {\n'
        "  count = 2\n"
        '  name  = "st"\n'
        "  lifecycle {\n    prevent_destroy = true\n  }\n"
        "  blob_properties {\n    versioning_enabled = true\n  }\n"
        '  timeouts {\n    create = "30m"\n  }\n'
        "}\n"
    )
    assert review_block(SCHEMA, block) == []


def test_resource_types_outside_the_schema_are_left_alone() -> None:
    block = _block('resource "azurerm_something_new" "a" {\n  whatever = 1\n}\n')
    assert review_block(SCHEMA, block) == []


def test_terraform_binary_lookup_never_raises() -> None:
    assert terraform_binary() is None or isinstance(terraform_binary(), str)
