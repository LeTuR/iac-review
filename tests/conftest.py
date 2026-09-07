from __future__ import annotations

from pathlib import Path

import pytest

from iac_review.core.cache import Cache

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "examples" / "fixture"
EXAMPLE = ROOT / "examples" / "output" / "platform.drawio"
EXAMPLE_SVG = ROOT / "examples" / "output" / "platform.drawio.svg"


@pytest.fixture
def cache() -> Cache:
    """The trimmed, frozen upstream data, so tests never touch the network."""
    return Cache(Path(__file__).parent / "data" / "cache", offline=True)
