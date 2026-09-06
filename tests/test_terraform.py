from __future__ import annotations

from iac_review.core.model import ChangedFile
from iac_review.providers.azure.terraform import parse

SOURCE = """resource "azurerm_resource_group" "rg" {
  name     = "rg-a"
  location = "westeurope"
}

data "azurerm_client_config" "current" {}

module "vnet" {
  source  = "Azure/avm-res-network-virtualnetwork/azurerm"
  version = "0.22.2"
}
"""


def test_blocks_carry_their_header_line() -> None:
    blocks, problems = parse(ChangedFile("main.tf", "modified", content=SOURCE))
    assert not problems
    by_address = {b.address: b for b in blocks}
    assert by_address["azurerm_resource_group.rg"].line == 1
    assert by_address["module.vnet"].line == 8
    assert by_address["data.azurerm_client_config.current"].kind == "data"


def test_module_type_is_its_source() -> None:
    blocks, _ = parse(ChangedFile("main.tf", "modified", content=SOURCE))
    module = next(b for b in blocks if b.kind == "module")
    assert module.type == "Azure/avm-res-network-virtualnetwork/azurerm"


def test_malformed_hcl_is_a_diagnostic_not_a_crash() -> None:
    blocks, problems = parse(ChangedFile("bad.tf", "modified", content='resource "a" {'))
    assert blocks == []
    assert len(problems) == 1
    assert "could not parse" in problems[0].message
