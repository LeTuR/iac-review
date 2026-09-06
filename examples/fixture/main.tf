# A deliberately mixed example: two hand-rolled resources that Azure Verified
# Modules already covers, one module that is already doing the right thing, and
# a resource type the drawio Azure library has no shape for.

resource "azurerm_resource_group" "platform" {
  name     = "rg-platform-weu"
  location = "westeurope"
}

resource "azurerm_storage_account" "state" {
  name                     = "stplatformstate"
  resource_group_name      = azurerm_resource_group.platform.name
  location                 = azurerm_resource_group.platform.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

resource "azurerm_key_vault" "platform" {
  name                = "kv-platform-weu"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
  tenant_id           = var.tenant_id
  sku_name            = "standard"
}

resource "azurerm_virtual_network" "hub" {
  name                = "vnet-hub-weu"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
  address_space       = ["10.0.0.0/16"]
}

resource "azurerm_subnet" "workload" {
  name                 = "snet-workload"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.hub.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Already an AVM module: this one draws no finding.
module "log_analytics" {
  source  = "Azure/avm-res-operationalinsights-workspace/azurerm"
  version = "0.4.2"

  name                = "log-platform-weu"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
}

variable "tenant_id" {
  type = string
}
