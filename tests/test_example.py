"""The committed example must be what the tool actually produces today."""

from __future__ import annotations

from iac_review.core.cache import Cache
from iac_review.core.drawio import render
from iac_review.core.review import review
from iac_review.local import changeset_from_path
from iac_review.providers.azure import AzureProvider
from tests.conftest import EXAMPLE, FIXTURE


def test_committed_example_matches_the_fixture(cache: Cache) -> None:
    result = review(changeset_from_path(FIXTURE), [AzureProvider(cache)])
    assert render(result.diagram) == EXAMPLE.read_text(), (
        "examples/output/platform.drawio is stale; regenerate it with "
        "IAC_REVIEW_CACHE=tests/data/cache uv run iac-review --offline review "
        "--path examples/fixture --diagram examples/output/platform.drawio"
    )


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
