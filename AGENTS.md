# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

## Working here

- Python with `uv`. `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run mypy`.
  Hooks run with `prek`, not the Python `pre-commit`.
- The architecture contract, and why the boundaries fall where they do:
  [docs/architecture.md](docs/architecture.md). It is enforced by
  `tests/test_architecture.py`, which walks the import graph — if you find
  yourself importing a forge from the core, the design is telling you something.

- The CLI is an [AXI](https://axi.md) (`axi/1.0-2026-07`). Output shape, error
  shape and exit codes are a contract, not a style: TOON on stdout, structured
  errors on stdout with a fixing command, stderr empty. `tests/test_cli.py`
  asserts it principle by principle — read those tests before changing output.
- The public skill is `skills/iac-review/SKILL.md`, installed by
  `npx skills add LeTuR/iac-review --skill iac-review`. Its body is vendored
  verbatim into other repositories, so it must never reference a path that only
  exists in this checkout, and its `description` is what makes an agent load it
  at the right moment.

## Sharp edges

- **Tests must never hit the network.** `tests/data/cache` is a trimmed, frozen
  copy of the upstream data, loaded through `Cache(..., offline=True)` by the
  `cache` fixture in `tests/conftest.py`. Adding a resource type to a test
  usually means adding its entries there too.
- **Both files in `examples/output/` are committed and tested.** After anything
  that changes diagram output, regenerate `platform.drawio` and
  `platform.drawio.svg` with the command in the failure message of
  `tests/test_example.py`. **Always pass `--offline`**: without it the run
  refreshes `tests/data/cache` in place and replaces the trimmed fixtures with
  full upstream payloads, which bloats the repository and destroys test
  determinism. `test_the_frozen_cache_stays_trimmed` catches that.
- **Both renderers place nodes through `core/layout.py`.** The `.drawio.svg`
  embeds the `.drawio` XML verbatim in its `content` attribute, so the picture
  and its source are one artifact; keep them rendering from the same layout or
  they will drift.
- **The AVM join is subtle.** A Terraform resource maps to an AVM module only
  when its ARM type path resolves to a single primary type. Leading scope
  segments (`subscriptions/resourceGroups`) are not parents; a real child
  (`storageAccounts/blobServices/containers`) has no module of its own. See
  `ArmType.primary`. Getting this wrong produces confident false findings, which
  is worse than no finding at all.
- **`core/toon.py` is a partial encoder on purpose.** It implements the forms
  this CLI emits, with the specification sections cited in the docstring. Adding
  a new output shape means checking the spec, not guessing.
- **Icon paths are drawio-relative** (`img/lib/azure2/...`) and resolved by
  drawio itself. Do not rewrite them to absolute URLs or embed the SVGs.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
