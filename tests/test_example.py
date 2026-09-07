"""The committed example must be what the tool actually produces today."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from iac_review.core.cache import Cache
from iac_review.core.drawio import render
from iac_review.core.review import review
from iac_review.core.svg import render as render_svg
from iac_review.local import changeset_from_path
from iac_review.providers.azure import AzureProvider
from tests.conftest import EXAMPLE, EXAMPLE_SVG, FIXTURE

_REGENERATE = (
    "stale; regenerate both examples with "
    "`uv run iac-review --cache tests/data/cache --offline review --path examples/fixture "
    "--diagram examples/output/platform.drawio` and again with `.drawio.svg`"
)


def test_committed_example_matches_the_fixture(cache: Cache) -> None:
    result = review(changeset_from_path(FIXTURE), [AzureProvider(cache)])
    assert render(result.diagram) == EXAMPLE.read_text(), f"platform.drawio is {_REGENERATE}"


def test_committed_svg_example_matches_the_fixture(cache: Cache) -> None:
    result = review(changeset_from_path(FIXTURE), [AzureProvider(cache)])
    rendered = render_svg(result.diagram, render(result.diagram), result.icons)
    assert rendered == EXAMPLE_SVG.read_text(), f"platform.drawio.svg is {_REGENERATE}"


def test_the_committed_svg_carries_the_committed_drawio_verbatim() -> None:
    """One artifact, not two to keep in sync: the picture holds its own source."""
    embedded = ET.fromstring(EXAMPLE_SVG.read_text()).get("content")
    assert embedded == EXAMPLE.read_text()


def test_the_committed_svg_displays_real_azure_icons() -> None:
    root = ET.fromstring(EXAMPLE_SVG.read_text())
    images = [e for e in root.iter("{http://www.w3.org/2000/svg}image")]
    assert len(images) == 5, "every mapped resource in the fixture draws its Azure icon"
    assert all((e.get("href") or "").startswith("data:image/svg+xml;base64,") for e in images)


def test_the_frozen_cache_stays_trimmed(cache: Cache) -> None:
    """Regenerating without --offline overwrites these with full upstream payloads."""
    from iac_review.providers.azure import sources

    arm_map = cache.path(sources.ARM_TYPE_MAP)
    index = cache.path(sources.AVM_INDEX)
    assert arm_map.stat().st_size < 20_000, "terraform-to-arm-types.json is not the trimmed fixture"
    assert index.stat().st_size < 20_000, "the AVM index is not the trimmed fixture"


def test_the_fixture_produces_avm_findings_and_reports_its_gaps(cache: Cache) -> None:
    result = review(changeset_from_path(FIXTURE), [AzureProvider(cache)])
    rules = {f.rule for f in result.findings}
    assert rules == {"azure/avm-module-available"}
    flagged = {f.line for f in result.findings}
    assert len(flagged) == 4

    sources = {d.source for d in result.diagnostics}
    assert "azure/icons" in sources, "an unmapped resource type must be reported"
    assert "azure/schema" in sources, "a skipped rule must say so"


def test_unmapped_resource_is_drawn_rather_than_dropped(cache: Cache) -> None:
    result = review(changeset_from_path(FIXTURE), [AzureProvider(cache)])
    unmapped = [n for n in result.diagram.nodes if n.kind == "azurerm_storage_container"]
    assert len(unmapped) == 1
    assert unmapped[0].icon is None
