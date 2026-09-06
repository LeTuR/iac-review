from __future__ import annotations

from pathlib import Path

import pytest

from iac_review.core.cache import Cache, Source

SOURCE = Source(key="nested/thing.json", url="https://example.invalid/thing.json", description="d")


def test_offline_without_a_cached_copy_is_an_explicit_failure(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="offline"):
        Cache(tmp_path, offline=True).fetch(SOURCE)


def test_offline_uses_a_cached_copy_and_says_it_is_stale(tmp_path: Path) -> None:
    target = tmp_path / SOURCE.key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"{}")
    entry = Cache(tmp_path, offline=True).fetch(SOURCE)
    assert entry.data == b"{}"
    assert entry.stale
    assert entry.note is not None


def test_a_failed_refresh_falls_back_to_the_cached_copy(tmp_path: Path) -> None:
    target = tmp_path / SOURCE.key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"cached")
    entry = Cache(tmp_path).fetch(SOURCE, refresh=True)
    assert entry.data == b"cached"
    assert entry.stale
    assert "refresh failed" in (entry.note or "")


def test_a_fetched_source_records_where_it_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Cache, "_download", staticmethod(lambda url, timeout=30: b"payload"))
    cache = Cache(tmp_path)
    entry = cache.fetch(SOURCE)
    assert entry.data == b"payload"
    meta = cache.meta(SOURCE)
    assert meta["url"] == SOURCE.url
    assert meta["bytes"] == 7
    assert meta["sha256"]
