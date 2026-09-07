"""Upstream data this provider depends on.

Every entry is fetched and cached at runtime rather than vendored, because all
three move on their own schedule: AVM publishes new modules, the Terraform-to-ARM
map follows new provider releases, and drawio's Azure library is refreshed
whenever Microsoft ships new icons.
"""

from __future__ import annotations

from iac_review.core.cache import Source

AVM_INDEX = Source(
    key="azure/avm-terraform-resource-modules.csv",
    url=(
        "https://raw.githubusercontent.com/Azure/Azure-Verified-Modules/main"
        "/docs/static/module-indexes/TerraformResourceModules.csv"
    ),
    description=(
        "Azure Verified Modules - Terraform resource module index (authoritative, versioned)"
    ),
)

ARM_TYPE_MAP = Source(
    key="azure/terraform-to-arm-types.json",
    url="https://raw.githubusercontent.com/magodo/aztft/main/internal/resmap/map.json",
    description=(
        "Terraform resource type to ARM resource type map, from the aztft library that "
        "backs Microsoft's Azure/aztfexport"
    ),
)

DRAWIO_ICON_CATALOGUE = Source(
    key="azure/drawio-azure2-icons.json",
    url="https://api.github.com/repos/jgraph/drawio/git/trees/dev?recursive=1",
    description="drawio Azure 2 shape library file listing, used to audit the icon map",
)

ALL = (AVM_INDEX, ARM_TYPE_MAP, DRAWIO_ICON_CATALOGUE)
