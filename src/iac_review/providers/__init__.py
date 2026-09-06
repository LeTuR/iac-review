"""Cloud provider modules.

A provider owns every rule and every icon decision for one cloud. Adding AWS
means adding a module here and one line in :func:`_install`; it never means
editing the core.
"""

from __future__ import annotations

from collections.abc import Callable

from iac_review.core.cache import Cache
from iac_review.core.model import Provider

_PROVIDERS: dict[str, Callable[[Cache], Provider]] = {}


def register(name: str, factory: Callable[[Cache], Provider]) -> None:
    _PROVIDERS[name] = factory


def get(name: str, cache: Cache) -> Provider:
    try:
        factory = _PROVIDERS[name]
    except KeyError:
        raise KeyError(
            f"unknown provider {name!r}; known: {', '.join(sorted(_PROVIDERS))}"
        ) from None
    return factory(cache)


def names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def _install() -> None:
    from iac_review.providers.azure import AzureProvider

    register("azure", AzureProvider)


_install()
