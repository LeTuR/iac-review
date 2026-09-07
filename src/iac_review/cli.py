"""The ``iac-review`` command line, built to the AXI specification.

AXI (axi/1.0-2026-07, https://axi.md) targets agents rather than humans: TOON on
stdout (§1), minimal schemas (§2), pre-computed aggregates (§4), definitive empty
states (§5), structured errors on stdout with actionable suggestions (§6),
content before help when invoked bare (§8), next steps on list output (§9), and
per-command ``--help`` with examples plus a ``--version`` fast path (§10).

Module-level imports stay in the standard library so ``--version`` and ``--help``
answer without loading the HCL parser or the provider graph (§10).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from iac_review import __version__
from iac_review.core import toon
from iac_review.core.cache import Cache
from iac_review.core.model import Finding, ReviewResult

DESCRIPTION = (
    "Review Terraform against Azure Verified Modules and the AzureRM provider "
    "schema, and diagram it with real Azure icons"
)
AXI_VERSION = "axi/1.0-2026-07"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_LEVELS = ("error", "warning", "info")
_VERSION_FLAGS = frozenset({"--version", "-v", "-V"})
_HELP_FLAGS = frozenset({"--help", "-h"})
_GLOBAL_FLAGS = {"--cache": "value", "--offline": "bare"}

_COMMANDS: dict[str, dict[str, str]] = {
    "review": {
        "--path": "value",
        "--target": "value",
        "--forge": "value",
        "--provider": "value",
        "--diagram": "value",
        "--format": "value",
        "--post": "bare",
        "--full": "bare",
        "--fail-on": "value",
    },
    "cache": {"--schema": "bare"},
    "icons": {},
}

_EXAMPLES = {
    "review": [
        "iac-review review --path infra --diagram infra.drawio",
        "iac-review review --target owner/repo#7 --post --fail-on error",
        "iac-review review --path infra --full --format json",
    ],
    "cache": [
        "iac-review cache status",
        "iac-review cache refresh",
        "iac-review cache refresh --schema",
    ],
    "icons": ["iac-review icons audit"],
}

_SUMMARIES = {
    "review": "Review a pull request or a directory of Terraform",
    "cache": "Show or refresh the upstream data the rules depend on",
    "icons": "Audit the Azure icon map against the shape library drawio ships",
}


class UsageError(Exception):
    """A malformed invocation. Carries its own help lines (§6)."""

    def __init__(self, message: str, help_lines: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.help_lines = list(help_lines)


class RunError(Exception):
    """The run could not be completed. Carries an actionable suggestion (§6)."""

    def __init__(self, message: str, help_lines: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.help_lines = list(help_lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # §10 version fast path: answered before the provider graph is imported.
    if args and args[0] in _VERSION_FLAGS and len(args) == 1:
        print(__version__)
        return EXIT_OK

    try:
        return _dispatch(args)
    except UsageError as exc:
        _emit_error(str(exc), exc.help_lines)
        return EXIT_USAGE
    except RunError as exc:
        _emit_error(str(exc), exc.help_lines)
        return EXIT_FAILED
    except (OSError, ValueError, KeyError) as exc:
        _emit_error(str(exc), ["Run `iac-review --help` for the available commands"])
        return EXIT_FAILED


def _emit_error(message: str, help_lines: Sequence[str]) -> None:
    """Errors are structured, on stdout, with a next step (§6)."""
    print(
        toon.document([toon.field("error", message)], toon.array("help", list(help_lines))), end=""
    )


def _take_globals(args: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Globals are always allowed, before the command or after it (§6)."""
    taken: dict[str, Any] = {}
    rest = list(args)
    while rest and rest[0].split("=")[0] in _GLOBAL_FLAGS:
        name, _, inline = rest[0].partition("=")
        if _GLOBAL_FLAGS[name] == "bare":
            taken[name] = True
            rest.pop(0)
            continue
        if inline:
            taken.setdefault(name, []).append(inline)
            rest.pop(0)
            continue
        if len(rest) < 2 or rest[1].startswith("-"):
            raise UsageError(
                f"{name} needs a value", ["e.g. iac-review --cache ~/.cache/iac-review"]
            )
        taken.setdefault(name, []).append(rest[1])
        del rest[:2]
    return taken, rest


def _dispatch(args: list[str]) -> int:
    leading, args = _take_globals(args)
    if not args:
        return _home()
    if args[0] in _VERSION_FLAGS:
        print(__version__)
        return EXIT_OK
    if args[0] in _HELP_FLAGS:
        print(_top_help(), end="")
        return EXIT_OK

    command, rest = args[0], args[1:]
    if command.startswith("-"):
        raise UsageError(
            f"unknown flag {command}",
            [f"valid commands: {', '.join(_COMMANDS)}", "Run `iac-review --help` for usage"],
        )
    if command not in _COMMANDS:
        raise UsageError(
            f"unknown command `{command}`",
            [f"valid commands: {', '.join(_COMMANDS)}", "Run `iac-review` to see current state"],
        )
    if any(flag in _HELP_FLAGS for flag in rest):
        print(_command_help(command), end="")
        return EXIT_OK

    flags, positional = _parse(command, rest)
    for name, value in leading.items():
        if isinstance(value, list):
            flags.setdefault(name, []).extend(value)
        else:
            flags[name] = value
    cache = _cache(flags)
    if command == "review":
        return _review(cache, flags)
    if command == "cache":
        return _cache_command(cache, flags, positional)
    return _icons(cache, positional)


def _parse(command: str, rest: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Reject unknown flags by name and list the valid ones inline (§6)."""
    known = {**_COMMANDS[command], **_GLOBAL_FLAGS}
    flags: dict[str, Any] = {}
    positional: list[str] = []
    index = 0
    while index < len(rest):
        token = rest[index]
        if not token.startswith("-"):
            positional.append(token)
            index += 1
            continue
        name, _, inline = token.partition("=")
        if name not in known:
            valid = ", ".join(sorted(known))
            raise UsageError(
                f"unknown flag {name} for `{command}`",
                [f"valid flags for `{command}`: {valid}", *_EXAMPLES[command][:1]],
            )
        if known[name] == "bare":
            flags[name] = True
            index += 1
            continue
        if inline:
            value = inline
            index += 1
        else:
            if index + 1 >= len(rest) or rest[index + 1].startswith("-"):
                raise UsageError(
                    f"{name} needs a value",
                    [f"e.g. {_EXAMPLES[command][0]}"],
                )
            value = rest[index + 1]
            index += 2
        flags.setdefault(name, [])
        if isinstance(flags[name], list):
            flags[name].append(value)
    return flags, positional


def _one(flags: dict[str, Any], name: str) -> str | None:
    got = flags.get(name)
    return got[-1] if isinstance(got, list) and got else None


def _cache(flags: dict[str, Any]) -> Cache:
    root = _one(flags, "--cache")
    return Cache(Path(root) if root else None, offline=bool(flags.get("--offline")))


def _home() -> int:
    """§8: bare invocation shows live, directory-scoped state, not a manual."""
    from iac_review.core.cache import Cache
    from iac_review.providers.azure import schema, sources

    cache = Cache()
    rows = []
    for source in sources.ALL:
        meta = cache.meta(source)
        rows.append(
            {
                "source": source.key.removeprefix("azure/"),
                "state": "cached" if meta else "missing",
                "bytes": int(meta.get("bytes", 0)) if meta else 0,
            }
        )
    rows.append(
        {
            "source": "azurerm-provider-schema.json",
            "state": "cached" if (cache.root / schema.CACHE_KEY).exists() else "missing",
            "bytes": 0,
        }
    )
    terraform = sorted(Path.cwd().rglob("*.tf"))
    missing = [row for row in rows if row["state"] == "missing"]

    help_lines = []
    if missing:
        help_lines.append("Run `iac-review cache refresh` to fetch the missing upstream data")
    help_lines.append(
        "Run `iac-review review --path <dir> --diagram <file>.drawio` to review a directory"
    )
    help_lines.append(
        "Run `iac-review review --target owner/repo#<n> --post` to review a pull request"
    )

    print(
        toon.document(
            [
                toon.field("bin", _executable()),
                toon.field("description", DESCRIPTION),
                toon.field("axi", AXI_VERSION),
            ],
            toon.table("cache", ("source", "state", "bytes"), rows),
            [toon.field("terraform", f"{len(terraform)} .tf file(s) under {_short(Path.cwd())}")],
            toon.array("help", help_lines),
        ),
        end="",
    )
    return EXIT_OK


def _review(cache: Cache, flags: dict[str, Any]) -> int:
    from iac_review import forges, providers
    from iac_review.core.drawio import render as render_drawio
    from iac_review.core.review import review as run_review
    from iac_review.local import changeset_from_path

    path, target = _one(flags, "--path"), _one(flags, "--target")
    if path and target:
        raise UsageError(
            "--path and --target are mutually exclusive",
            ["Use --path for a directory on disk, --target for a pull request"],
        )
    if not path and not target:
        raise UsageError(
            "review needs --path or --target",
            [_EXAMPLES["review"][0], _EXAMPLES["review"][1]],
        )

    fail_on = _one(flags, "--fail-on")
    if fail_on is not None and fail_on not in _LEVELS:
        raise UsageError(
            f"--fail-on must be one of {', '.join(_LEVELS)}, not {fail_on!r}",
            ["e.g. iac-review review --path infra --fail-on error"],
        )
    output = _one(flags, "--format") or "toon"
    if output not in ("toon", "json"):
        raise UsageError(
            f"--format must be toon or json, not {output!r}",
            ["e.g. iac-review review --path infra --format json"],
        )

    forge = None
    if path:
        source = Path(path)
        if not source.is_dir():
            raise RunError(
                f"{path} is not a directory",
                ["Pass a directory containing .tf files, e.g. `--path infra`"],
            )
        changeset = changeset_from_path(source)
    else:
        forge_name = _one(flags, "--forge") or "github"
        if forge_name not in forges.names():
            raise UsageError(
                f"unknown forge {forge_name!r}",
                [f"known forges: {', '.join(forges.names())}"],
            )
        forge = forges.get(forge_name)
        try:
            changeset = forge.fetch(str(target))
        except NotImplementedError as exc:
            raise RunError(str(exc), ["Use --forge github, or --path for a local review"]) from exc

    chosen = flags.get("--provider") or list(providers.names())
    unknown = [name for name in chosen if name not in providers.names()]
    if unknown:
        raise UsageError(
            f"unknown provider {unknown[0]!r}",
            [f"known providers: {', '.join(providers.names())}"],
        )
    result = run_review(changeset, [providers.get(name, cache) for name in chosen])

    diagram_path = _one(flags, "--diagram")
    if diagram_path:
        written = Path(diagram_path)
        written.parent.mkdir(parents=True, exist_ok=True)
        drawio_xml = render_drawio(result.diagram)
        if written.name.endswith(".svg"):
            from iac_review.core.svg import render as render_svg

            written.write_text(render_svg(result.diagram, drawio_xml, result.icons))
        else:
            written.write_text(drawio_xml)
        result = replace(result, diagram_path=_repo_relative(written))

    if flags.get("--post"):
        if forge is None:
            raise UsageError(
                "--post needs --target",
                ["A --path review has no pull request to post to; add --target owner/repo#<n>"],
            )
        forge.publish(result)

    if output == "json":
        print(_json(result, diagram_path))
    else:
        print(_toon_review(result, diagram_path, full=bool(flags.get("--full"))), end="")

    if fail_on and any(
        _LEVELS.index(f.severity) <= _LEVELS.index(fail_on) for f in result.findings
    ):
        return EXIT_FAILED
    return EXIT_OK


def _location(f: Finding) -> str:
    if not f.path:
        return "-"
    if f.line is None:
        return f.path
    return f"{f.path}:{f.line}"


def _toon_review(result: ReviewResult, diagram: str | None, *, full: bool) -> str:
    counts = {level: sum(1 for f in result.findings if f.severity == level) for level in _LEVELS}
    breakdown = ", ".join(f"{n} {level}" for level, n in counts.items() if n) or "none"
    reviewed = len(result.changeset.by_suffix(".tf"))

    sections: list[list[str]] = [
        toon.block(
            "review",
            {
                "source": result.changeset.ref,
                "origin": result.changeset.origin,
                "files": reviewed,
                "findings": f"{len(result.findings)} ({breakdown})",
            },
        )
    ]

    if result.findings:
        sections.append(
            toon.table(
                "findings",
                ("severity", "location", "rule", "title"),
                [
                    {
                        "severity": f.severity,
                        "location": _location(f),
                        "rule": f.rule,
                        "title": f.title,
                    }
                    for f in result.findings
                ],
            )
        )
        if full:
            # One tabular array rather than repeated `finding:` blocks: sibling
            # keys must be unique (TOON §14.3), and a header costs fewer tokens.
            sections.append(
                toon.table(
                    "details",
                    ("location", "detail", "suggestion", "references"),
                    [
                        {
                            "location": _location(f),
                            "detail": f.detail,
                            "suggestion": f.suggestion or "-",
                            "references": " ".join(f.references) or "-",
                        }
                        for f in result.findings
                    ],
                )
            )
    else:
        # §5: state the zero with context so the answer is unambiguous.
        sections.append([toon.field("findings", f"0 findings in {reviewed} terraform file(s)")])

    if diagram:
        sections.append(
            toon.block(
                "diagram",
                {
                    "path": diagram,
                    "nodes": len(result.diagram.nodes),
                    "edges": len(result.diagram.edges),
                    "unmapped": sum(1 for n in result.diagram.nodes if n.icon is None),
                },
            )
        )

    sections.append(
        toon.table(
            "notes",
            ("source", "message"),
            [{"source": d.source, "message": d.message} for d in result.diagnostics],
        )
    )

    help_lines: list[str] = []
    if result.findings and not full:
        help_lines.append(
            "Run the same command with `--full` for each finding's detail and suggestion"
        )
    if result.findings and result.changeset.origin != "local":
        help_lines.append("Add `--post` to publish these findings as one review")
    if not diagram:
        help_lines.append("Add `--diagram <file>.drawio` to draw the infrastructure")
    if any(d.source == "azure/schema" for d in result.diagnostics):
        help_lines.append(
            "Run `iac-review cache refresh --schema` to enable the provider schema rules"
        )
    sections.append(toon.array("help", help_lines))
    return toon.document(*sections)


def _cache_command(cache: Cache, flags: dict[str, Any], positional: list[str]) -> int:
    from iac_review.providers.azure import schema, sources

    action = positional[0] if positional else "status"
    if action not in ("status", "refresh"):
        raise UsageError(
            f"unknown action `{action}` for `cache`",
            ["valid actions: status, refresh", _EXAMPLES["cache"][0]],
        )

    rows: list[dict[str, Any]] = []
    if action == "refresh":
        for source in sources.ALL:
            entry = cache.fetch(source, refresh=True)
            rows.append(
                {
                    "source": source.key.removeprefix("azure/"),
                    "state": "stale" if entry.stale else "refreshed",
                    "bytes": len(entry.data),
                }
            )
        if flags.get("--schema"):
            try:
                generated = schema.generate(cache)
            except RuntimeError as exc:
                raise RunError(
                    str(exc),
                    [
                        "Install terraform or tofu, then re-run "
                        "`iac-review cache refresh --schema`",
                        "Without it the schema rules are skipped and everything else still runs",
                    ],
                ) from exc
            rows.append(
                {
                    "source": "azurerm-provider-schema.json",
                    "state": "generated",
                    "bytes": generated.stat().st_size,
                }
            )
    else:
        for source in sources.ALL:
            meta = cache.meta(source)
            rows.append(
                {
                    "source": source.key.removeprefix("azure/"),
                    "state": "cached" if meta else "missing",
                    "bytes": int(meta.get("bytes", 0)) if meta else 0,
                }
            )
        path = cache.root / schema.CACHE_KEY
        rows.append(
            {
                "source": "azurerm-provider-schema.json",
                "state": "cached" if path.exists() else "missing",
                "bytes": path.stat().st_size if path.exists() else 0,
            }
        )

    help_lines = []
    if any(row["state"] == "missing" for row in rows):
        help_lines.append("Run `iac-review cache refresh` to fetch what is missing")
    if not flags.get("--schema") and any(
        row["source"] == "azurerm-provider-schema.json" and row["state"] == "missing"
        for row in rows
    ):
        help_lines.append(
            "Run `iac-review cache refresh --schema` to enable the provider schema rules"
        )
    print(
        toon.document(
            [toon.field("root", _short(cache.root))],
            toon.table("sources", ("source", "state", "bytes"), rows),
            toon.array("help", help_lines),
        ),
        end="",
    )
    return EXIT_OK


def _icons(cache: Cache, positional: list[str]) -> int:
    import json

    from iac_review.providers.azure import sources
    from iac_review.providers.azure.icons import IconMap

    action = positional[0] if positional else "audit"
    if action != "audit":
        raise UsageError(
            f"unknown action `{action}` for `icons`",
            ["valid actions: audit", _EXAMPLES["icons"][0]],
        )
    try:
        entry = cache.fetch(sources.DRAWIO_ICON_CATALOGUE)
    except (OSError, ValueError) as exc:
        raise RunError(
            f"the drawio icon catalogue is not available ({exc})",
            ["Run `iac-review cache refresh` to fetch it"],
        ) from exc

    marker = "src/main/webapp/img/lib/azure2/"
    catalogue = {
        item["path"][len(marker) :]
        for item in json.loads(entry.data).get("tree", [])
        if isinstance(item.get("path"), str) and item["path"].startswith(marker)
    }
    mapped = IconMap.load().shapes
    missing = sorted(mapped - catalogue)

    sections = [
        toon.block(
            "icons",
            {"library": len(catalogue), "mapped": len(mapped), "missing": len(missing)},
        )
    ]
    if missing:
        sections.append(toon.table("missing", ("shape",), [{"shape": shape} for shape in missing]))
        sections.append(
            toon.array(
                "help",
                [
                    "These shapes were renamed or removed upstream; update "
                    "src/iac_review/providers/azure/data/icons.json or your "
                    "IAC_REVIEW_AZURE_ICONS override"
                ],
            )
        )
    else:
        sections.append([toon.field("status", "every mapped shape exists in the drawio library")])
    print(toon.document(*sections), end="")
    return EXIT_FAILED if missing else EXIT_OK


def _json(result: ReviewResult, diagram: str | None) -> str:
    import json

    return json.dumps(
        {
            "changeset": {"ref": result.changeset.ref, "origin": result.changeset.origin},
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "title": f.title,
                    "detail": f.detail,
                    "path": f.path,
                    "line": f.line,
                    "suggestion": f.suggestion,
                    "references": list(f.references),
                }
                for f in result.findings
            ],
            "diagnostics": [{"source": d.source, "message": d.message} for d in result.diagnostics],
            "diagram": diagram,
        },
        indent=2,
    )


def _top_help() -> str:
    return toon.document(
        [
            toon.field("bin", _executable()),
            toon.field("description", DESCRIPTION),
            toon.field("usage", "iac-review [command] [flags]"),
        ],
        toon.table(
            "commands",
            ("command", "summary"),
            [{"command": name, "summary": _SUMMARIES[name]} for name in _COMMANDS],
        ),
        toon.array("global_flags", ["--cache <dir>", "--offline", "--help", "--version"]),
        toon.array(
            "help",
            [
                "Run `iac-review` with no arguments to see current state",
                "Run `iac-review <command> --help` for that command's flags and examples",
            ],
        ),
    )


def _command_help(command: str) -> str:
    flags = {**_COMMANDS[command], **_GLOBAL_FLAGS}
    rendered = [
        {"flag": name, "takes": "value" if kind == "value" else "-"}
        for name, kind in sorted(flags.items())
    ]
    sections = [
        [
            toon.field("command", f"iac-review {command}"),
            toon.field("description", _SUMMARIES[command]),
        ]
    ]
    if command == "cache":
        sections.append(toon.array("actions", ["status", "refresh"]))
    if command == "icons":
        sections.append(toon.array("actions", ["audit"]))
    sections.append(toon.table("flags", ("flag", "takes"), rendered))
    if command == "review":
        sections.append(
            toon.array("fail_on", list(_LEVELS)),
        )
    sections.append(toon.array("examples", _EXAMPLES[command]))
    sections.append(
        toon.array(
            "exit_codes", ["0 success", "1 the run failed or --fail-on was met", "2 usage error"]
        )
    )
    return toon.document(*sections)


def _repo_relative(path: Path) -> str | None:
    """Path as a forge would address it, or ``None`` when it is outside the tree.

    A forge can only display a file that lives in the repository, so a diagram
    written to ``/tmp`` is deliberately not offered as one.
    """
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return None


def _executable() -> str:
    return _short(Path(sys.argv[0]).resolve()) if sys.argv and sys.argv[0] else "iac-review"


def _short(path: Path) -> str:
    home = os.path.expanduser("~")
    text = str(path)
    return text.replace(home, "~", 1) if text.startswith(home) else text
