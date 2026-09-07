"""How the Azure provider turns Terraform into diagram nodes."""

from __future__ import annotations

from iac_review.core.cache import Cache
from iac_review.core.model import ChangedFile, Changeset
from iac_review.providers.azure import AzureProvider

SOURCE = """resource "azurerm_resource_group" "platform" {
  name     = "rg-platform"
  location = "westeurope"
}

resource "azurerm_storage_account" "state" {
  name                = "stplatform"
  resource_group_name = azurerm_resource_group.platform.name
}

resource "azurerm_storage_container" "tfstate" {
  name               = "tfstate"
  storage_account_id = azurerm_storage_account.state.id
}

resource "azurerm_dns_zone" "orphan" {
  name = "example.com"
}
"""


def _nodes(cache: Cache) -> dict[str, object]:
    changeset = Changeset(ref="t", files=(ChangedFile("main.tf", "modified", content=SOURCE),))
    result = AzureProvider(cache).analyze(changeset)
    return {node.label: node for node in result.nodes}


def test_a_resource_group_heads_its_own_box(cache: Cache) -> None:
    assert _nodes(cache)["platform"].group == "platform"  # type: ignore[attr-defined]


def test_a_resource_naming_a_resource_group_joins_it(cache: Cache) -> None:
    assert _nodes(cache)["state"].group == "platform"  # type: ignore[attr-defined]


def test_a_child_resource_inherits_its_parents_group(cache: Cache) -> None:
    """The container names no resource group; its storage account does."""
    assert _nodes(cache)["tfstate"].group == "platform"  # type: ignore[attr-defined]


def test_a_resource_with_no_owner_falls_back_to_its_file(cache: Cache) -> None:
    assert _nodes(cache)["orphan"].group == "main.tf"  # type: ignore[attr-defined]


def test_icons_are_offered_so_a_standalone_image_can_embed_them(cache: Cache) -> None:
    changeset = Changeset(ref="t", files=(ChangedFile("main.tf", "modified", content=SOURCE),))
    result = AzureProvider(cache).analyze(changeset)
    assert result.icons is not None
    assert result.icons.read("img/lib/azure2/storage/Storage_Accounts.svg")
    assert result.icons.read("img/lib/azure2/nope/Missing.svg") is None
    assert result.icons.read("../../etc/passwd") is None
