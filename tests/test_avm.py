from __future__ import annotations

from iac_review.core.cache import Cache
from iac_review.core.model import ChangedFile
from iac_review.providers.azure.armtypes import ArmType, ArmTypeMap
from iac_review.providers.azure.avm import AvmIndex, review_block
from iac_review.providers.azure.terraform import Block, parse


def _block(cache: Cache, source: str, address: str) -> tuple[Block, ArmType | None]:
    blocks, _ = parse(ChangedFile("main.tf", "modified", content=source))
    block = next(b for b in blocks if b.address == address)
    return block, ArmTypeMap.load(cache).get(block.type)


def test_hand_rolled_resource_is_flagged_with_a_pinned_module(cache: Cache) -> None:
    source = 'resource "azurerm_storage_account" "state" {\n  name = "st"\n}\n'
    block, arm_type = _block(cache, source, "azurerm_storage_account.state")
    finding = review_block(cache, AvmIndex.load(cache), block, arm_type)
    assert finding is not None
    assert finding.severity == "warning"
    assert finding.line == 1
    assert finding.suggestion is not None
    assert 'source  = "Azure/avm-res-storage-storageaccount/azurerm"' in finding.suggestion
    assert 'version = "0.10.0"' in finding.suggestion
    assert any("registry.terraform.io" in url for url in finding.references)


def test_child_resources_are_not_flagged(cache: Cache) -> None:
    source = 'resource "azurerm_storage_container" "c" {\n  name = "x"\n}\n'
    block, arm_type = _block(cache, source, "azurerm_storage_container.c")
    assert review_block(cache, AvmIndex.load(cache), block, arm_type) is None


def test_a_module_block_is_never_flagged(cache: Cache) -> None:
    source = 'module "sa" {\n  source = "Azure/avm-res-storage-storageaccount/azurerm"\n}\n'
    block, arm_type = _block(cache, source, "module.sa")
    assert review_block(cache, AvmIndex.load(cache), block, arm_type) is None


def test_only_available_modules_are_recommended(cache: Cache) -> None:
    index = AvmIndex.load(cache)
    unknown = ArmType("Microsoft.Nowhere", ("things",))
    assert index.available_for(unknown) is None
