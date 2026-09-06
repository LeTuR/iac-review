# iac-review

Reviews an Infrastructure-as-Code change and posts the result back to the pull
request: findings anchored to the lines that changed, plus a drawio diagram of
the infrastructure drawn with the real Azure icons.

Today it reviews Terraform targeting Azure, on GitHub. That is a deliberate
slice, not the plan — see [What it does not do yet](#what-it-does-not-do-yet).

```mermaid
flowchart LR
  subgraph forge["forge adapter"]
    GH["GitHub"]
    GL["GitLab (gap)"]
  end
  subgraph core["core - no forge, no cloud"]
    CS["Changeset"] --> RV["review()"] --> FD["Findings"]
    RV --> DG["Diagram"] --> DX["drawio XML"]
  end
  subgraph provider["provider module"]
    AZ["azure: AVM + schema rules, icon map"]
  end
  GH -->|"PR to Changeset"| CS
  RV <--> AZ
  FD -->|"Findings to review comments"| GH
```

The core never imports a forge type or a cloud type. Adding GitLab, or adding
AWS, is adding a module. [`tests/test_architecture.py`](tests/test_architecture.py)
enforces that by walking the imports, so the claim cannot quietly stop being true.

## Install

As an agent skill, which is how it is meant to be used:

```console
$ npx skills add LeTuR/iac-review --skill iac-review
```

That vendors [`skills/iac-review/SKILL.md`](skills/iac-review/SKILL.md) into your
agent. The skill body stands alone and reaches the CLI through `uvx`, so it
works without a clone.

As a CLI on its own:

```console
$ uvx --from git+https://github.com/LeTuR/iac-review iac-review
```

## Try it

```console
$ uv run iac-review review --path examples/fixture --diagram /tmp/platform.drawio
review:
  source: examples/fixture
  origin: local
  files: 1
  findings: 4 (4 warning)
findings[4]{severity,location,rule,title}:
  warning,"main.tf:5",azure/avm-module-available,Use the AVM module for Resource Group
  warning,"main.tf:10",azure/avm-module-available,Use the AVM module for Storage Account
  warning,"main.tf:25",azure/avm-module-available,Use the AVM module for Key Vault
  warning,"main.tf:33",azure/avm-module-available,Use the AVM module for Virtual Network
diagram:
  path: /tmp/platform.drawio
  nodes: 6
  edges: 6
  unmapped: 1
notes[2]{source,message}:
  azure/schema,"AzureRM provider schema is not cached, so schema rules were skipped"
  azure/icons,no Azure shape mapped for azurerm_storage_container
help[2]: ...
```

Against a pull request:

```console
$ iac-review review --target LeTuR/iac-review#7 --post --fail-on error
```

`--post` opens one GitHub review: findings that land on a changed line become
inline comments, the rest go in the review body.

## The CLI is an AXI

It follows [AXI](https://axi.md) `axi/1.0-2026-07`, so an agent can drive it
without reading a manual: TOON on stdout, minimal list schemas with the totals
pre-computed, definitive empty states, structured errors on stdout carrying the
command that fixes them, live state when invoked bare, and `--help` per command
with worked examples.

```console
$ iac-review review --pathh infra
error: unknown flag --pathh for `review`
help[2]: "valid flags for `review`: --cache, --diagram, --fail-on, ...",iac-review review --path infra --diagram infra.drawio
```

Exit codes: 0 success, 1 the run failed or `--fail-on` was met, 2 usage error.

The TOON encoder is [`core/toon.py`](src/iac_review/core/toon.py) — about sixty
lines covering the three forms this CLI emits, written against the specification
rather than taken as a 0.1.0 dependency. Session hooks (AXI §7) are not shipped:
a stateless reviewer has no per-directory live state worth loading into every
session, and the spec offers the installable skill as the complementary path.

## What it checks

**Azure Verified Modules.** A hand-rolled `azurerm_*` resource that AVM already
publishes a module for is a finding, with the registry source and the current
version in the suggested replacement. This is the highest-value check because it
tests a policy rather than syntax, and because AVM modules carry the WAF-aligned
defaults, diagnostics, private-endpoint and RBAC wiring that a bare resource
does not.

Child resources are not flagged. `azurerm_storage_container` resolves to
`Microsoft.Storage/storageAccounts/blobServices/containers`, which has no
top-level module of its own — the storage account module owns it.

**Provider schema.** `terraform providers schema -json` is authoritative for
what will actually apply, so an argument the AzureRM provider does not define is
an error. This needs `terraform` (or `tofu`) on `PATH`; without it the rule
reports itself skipped rather than failing the run:

```console
$ iac-review cache refresh --schema
```

## The diagram

`--diagram` writes an uncompressed `.drawio` file that opens in drawio desktop
and app.diagrams.net. Nodes use drawio's own Azure 2 shape library, resources
are grouped by the resource group they reference, and edges follow the
interpolations between resources.

[`examples/output/platform.drawio`](examples/output/platform.drawio) is generated
from [`examples/fixture`](examples/fixture) and committed, so the output is
reviewable rather than described. A test regenerates it and fails when it drifts.

The icon mapping is data, not code:
[`src/iac_review/providers/azure/data/icons.json`](src/iac_review/providers/azure/data/icons.json).
Point `IAC_REVIEW_AZURE_ICONS` at your own file to override it. An unmapped
resource type is drawn as a labelled generic shape and reported as a diagnostic
— never dropped, never fatal. drawio's Azure library lags Microsoft's icon set,
so `iac-review icons audit` compares the map against the library drawio ships
today, and a weekly CI job runs it.

## Where the facts come from

Nothing is vendored. All three sources move independently, so they are fetched
and cached under `$XDG_CACHE_HOME/iac-review`, and `iac-review cache refresh`
re-pulls them. `iac-review cache status` shows what is cached, from where, and
when.

| Source | Used for | Why this one |
| --- | --- | --- |
| [AVM Terraform resource module index](https://azure.github.io/Azure-Verified-Modules/module-indexes/TerraformResourceModules.csv) | which ARM types have a published module | AVM publishes it as structured CSV and keeps it current, so there is nothing to scrape |
| [aztft resource map](https://github.com/magodo/aztft) | Terraform resource type to ARM resource type | the join key between the two worlds; this is the library behind Microsoft's [`Azure/aztfexport`](https://github.com/Azure/aztfexport) |
| [Terraform Registry](https://registry.terraform.io) | current version of a recommended module | where the version actually lives |
| `terraform providers schema -json` | every resource, argument and requiredness | machine-readable, local, and authoritative for the provider version you pin |
| [drawio Azure 2 shape library](https://github.com/jgraph/drawio/tree/dev/src/main/webapp/img/lib/azure2) | the icons | drawio resolves these paths itself, so the diagram needs no embedded assets |

Prose documentation is a last resort, used only for semantics no schema carries.
Cloning the Azure docs repository was considered and rejected: the provider
schema answers "is this valid" exactly, offline, per provider version.

The one source that is not published by Microsoft is `aztft`. It is a
dependency of Microsoft's own `aztfexport`, it is cached and refreshable like
everything else, and a wrong entry can only mean a missed or misattributed AVM
suggestion — never a bad `terraform apply`.

## What it does not do yet

- **GitLab.** [`src/iac_review/forges/gitlab.py`](src/iac_review/forges/gitlab.py)
  is the shape of the gap: the class exists, is registered, raises
  `NotImplementedError`, and its docstring names the exact REST calls to fill
  in. GitLab's diffs are the same unified format, which is why the parser lives
  in the core. Nothing outside that file changes.
- **Clouds other than Azure.** `iac_review/providers/` takes a second module and
  one line in `_install()`.
- **IaC other than Terraform.** The parser is Terraform-specific and lives in
  the Azure provider.
- **A rule library.** Two rules ship. This is a skeleton with one working
  vertical slice, not a linter.
- **ARM resource-provider schemas**, the third validation source, for semantics
  the Terraform provider schema cannot express.

## Development

```console
$ uv sync
$ uv run pytest
$ prek install
```

`prek run --all-files` runs the same hooks CI does, including checkov. The
example fixture is excluded from checkov in [`.checkov.yaml`](.checkov.yaml):
it is deliberately non-conformant Terraform, and making it pass would delete the
findings it exists to produce.

There is no `terraform_fmt` hook. The only Terraform here is that one fixture,
and requiring a Terraform install to commit a Python change is a bad trade; the
fixture is hand-kept in canonical form.

The test suite runs entirely against `tests/data/cache`, a trimmed and frozen
copy of the upstream data, so it never touches the network and never changes
its mind when AVM ships a release.

Hooks run with [`prek`](https://github.com/j178/prek), not the Python
`pre-commit`. Dependency updates come from Renovate.
