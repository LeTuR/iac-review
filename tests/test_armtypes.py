from __future__ import annotations

from iac_review.core.cache import Cache
from iac_review.providers.azure.armtypes import ArmType, ArmTypeMap


def test_single_segment_type_is_primary() -> None:
    assert ArmType("Microsoft.Storage", ("storageAccounts",)).key == (
        "microsoft.storage/storageaccounts"
    )


def test_leading_scope_segments_are_not_parents() -> None:
    resource_group = ArmType("Microsoft.Resources", ("subscriptions", "resourceGroups"))
    assert resource_group.key == "microsoft.resources/resourcegroups"


def test_child_resources_have_no_primary_type() -> None:
    container = ArmType("Microsoft.Storage", ("storageAccounts", "blobServices", "containers"))
    assert container.primary is None
    assert container.key is None
    assert container.full == "Microsoft.Storage/storageAccounts/blobServices/containers"


def test_map_resolves_real_terraform_types(cache: Cache) -> None:
    mapping = ArmTypeMap.load(cache)
    storage_account = mapping.get("azurerm_storage_account")
    subnet = mapping.get("azurerm_subnet")
    assert storage_account is not None and subnet is not None
    assert storage_account.key == "microsoft.storage/storageaccounts"
    assert subnet.key is None
    assert mapping.get("azurerm_not_a_real_resource") is None
