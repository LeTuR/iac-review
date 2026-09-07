"""Forge adapters.

An adapter is the only place that knows what a pull request or a merge request
is. It converts one into a :class:`~iac_review.core.model.Changeset` and converts
:class:`~iac_review.core.model.Finding` objects back into review comments.
Adding a forge means adding a module here; it never means editing the core.
"""

from __future__ import annotations

from collections.abc import Callable

from iac_review.core.model import Forge

_ADAPTERS: dict[str, Callable[[], Forge]] = {}


def register(name: str, factory: Callable[[], Forge]) -> None:
    _ADAPTERS[name] = factory


def get(name: str) -> Forge:
    try:
        factory = _ADAPTERS[name]
    except KeyError:
        raise KeyError(f"unknown forge {name!r}; known: {', '.join(sorted(_ADAPTERS))}") from None
    return factory()


def names() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def _install() -> None:
    from iac_review.forges.github import GitHubForge
    from iac_review.forges.gitlab import GitLabForge

    register("github", GitHubForge)
    register("gitlab", GitLabForge)


_install()
