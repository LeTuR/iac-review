# Architecture

The captain asked for a reviewer that is "maybe forge agnostic". This is what
that means structurally rather than aspirationally.

```
  forge adapter          normalized            core review           normalized
  (GitHub / GitLab)  ->   changeset      ->   (no forge, no cloud)  ->  findings
                                                     |                      |
                                                provider module        forge adapter
                                                 (azure first)          (post back)
```

## The rule

`iac_review/core/` may not import `iac_review.forges` or
`iac_review.providers`. A provider may not import a forge, and a forge may not
import a provider. Wiring happens in two registries that sit above the core:
`iac_review/forges/__init__.py` and `iac_review/providers/__init__.py`.

`tests/test_architecture.py` walks the import graph and fails when any of that
stops being true. It is the reason the claim survives a second forge.

## Who owns what

| Layer | Knows about | Does not know about |
| --- | --- | --- |
| `core/` | changesets, findings, diagrams, unified diffs, the drawio file format, TOON, HTTP caching | pull requests, merge requests, Azure, Terraform |
| `forges/` | pull requests, merge requests, review APIs, tokens | clouds, Terraform, rules |
| `providers/azure/` | Terraform, ARM types, AVM, the AzureRM schema, Azure icons | pull requests, merge requests |

Two details earn their place in the core rather than in an adapter:

- **Unified diff parsing** (`core/diff.py`). It is a patch format, not a forge
  feature. GitHub's `patch` field and GitLab's `diff` field are the same format,
  so the second adapter reuses it untouched.
- **The drawio renderer** (`core/drawio.py`). drawio is an output format, not a
  cloud. A node arrives carrying the icon its provider chose; the renderer never
  asks what the node is. An AWS provider would reuse it unchanged.
- **The TOON encoder** (`core/toon.py`). Same argument: an output format the CLI
  needs, with no knowledge of what is being encoded.

## Adding a forge

Write a class with `name`, `fetch(target) -> Changeset` and
`publish(result) -> None`, then register it. Nothing else moves.
`forges/gitlab.py` already carries the exact API calls in its docstring.

## Adding a cloud

Write a class with `name` and `analyze(changeset) -> ProviderResult`, returning
findings and diagram nodes with icons already resolved, then register it in
`providers/_install()`.

A provider that raises does not abort the run: `core/review.py` turns the failure
into a diagnostic so one broken provider cannot lose another's findings.

## Degrading rather than failing

Three things are expected to be missing, and none of them stops a review:

| Missing | Behaviour |
| --- | --- |
| an icon for a resource type | labelled generic shape, reported as a diagnostic |
| the AzureRM provider schema | schema rules skipped, reported as a diagnostic |
| the network | cached copies used, marked stale |
