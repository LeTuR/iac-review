"""The CLI as an AXI: structured stdout, actionable errors, honest exit codes.

Principle numbers refer to the AXI specification, axi/1.0-2026-07.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from iac_review import __version__
from iac_review.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, _toon_review, main
from iac_review.core.model import Changeset, Finding, ReviewResult
from tests.conftest import FIXTURE

CACHE = str(Path(__file__).parent / "data" / "cache")


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(["--cache", CACHE, "--offline", *argv])
    captured = capsys.readouterr()
    assert captured.err == "", "AXI keeps stdout structured and stderr empty (§6)"
    return code, captured.out


def test_review_emits_toon_with_aggregates(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--path", str(FIXTURE))
    assert code == EXIT_OK
    assert "findings: 4 (4 warning)" in out  # §4 pre-computed aggregate
    assert "findings[4]{severity,location,rule,title}:" in out  # §1, §2
    assert "notes[2]{source,message}:" in out
    assert out.startswith("review:")


def test_full_adds_detail_the_list_omits(capsys: pytest.CaptureFixture[str]) -> None:
    _, brief = _run(capsys, "review", "--path", str(FIXTURE))
    _, full = _run(capsys, "review", "--path", str(FIXTURE), "--full")
    assert "details[" not in brief  # §2 lists stay minimal
    assert "details[4]{location,detail,suggestion,references}:" in full  # §3
    assert "avm-res-storage-storageaccount/azurerm" in full
    assert "Run the same command with `--full`" in brief  # §9 it is discoverable


def test_location_falls_back_to_path_when_line_is_unknown() -> None:
    result = ReviewResult(
        changeset=Changeset(ref="local", files=()),
        findings=(Finding("azure/other", "info", "No line", "d", "main.tf"),),
    )
    out = _toon_review(result, None, full=True)
    assert "main.tf:None" not in out
    assert "main.tf" in out


def test_empty_result_states_the_zero(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('variable "unused" {\n  type = string\n}\n')
    code, out = _run(capsys, "review", "--path", str(tmp_path))
    assert code == EXIT_OK
    assert "findings: 0 findings in 1 terraform file(s)" in out  # §5


def test_diagram_reports_what_it_drew(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    target = tmp_path / "out" / "d.drawio"
    _, out = _run(capsys, "review", "--path", str(FIXTURE), "--diagram", str(target))
    assert "nodes: 6" in out
    assert "unmapped: 1" in out
    assert target.read_text().startswith("<?xml")


def test_json_format_is_still_available(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--path", str(FIXTURE), "--format", "json")
    assert code == EXIT_OK
    assert {f["rule"] for f in json.loads(out)["findings"]} == {"azure/avm-module-available"}


def test_fail_on_warning_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(capsys, "review", "--path", str(FIXTURE), "--fail-on", "warning")
    assert code == EXIT_FAILED


def test_fail_on_error_ignores_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = _run(capsys, "review", "--path", str(FIXTURE), "--fail-on", "error")
    assert code == EXIT_OK


def test_unknown_flag_is_rejected_by_name_with_the_valid_ones(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = _run(capsys, "review", "--pathh", "x")
    assert code == EXIT_USAGE  # §6
    assert "error: unknown flag --pathh for `review`" in out
    assert "--path" in out and "--target" in out  # inline help, one-turn correction
    assert "help[" in out


def test_unknown_command_lists_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "nope")
    assert code == EXIT_USAGE
    assert "error: unknown command `nope`" in out
    assert "review, cache, icons" in out


def test_missing_source_names_both_ways_to_supply_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = _run(capsys, "review")
    assert code == EXIT_USAGE
    assert "--path or --target" in out
    assert "iac-review review --path infra" in out


def test_bad_enum_values_say_what_is_allowed(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--path", str(FIXTURE), "--fail-on", "nope")
    assert code == EXIT_USAGE
    assert "error, warning, info" in out


def test_flag_needing_a_value_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--path")
    assert code == EXIT_USAGE
    assert "--path needs a value" in out


def test_posting_a_path_review_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--path", str(FIXTURE), "--post")
    assert code == EXIT_USAGE
    assert "--post needs --target" in out


def test_missing_directory_is_an_error_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = _run(capsys, "review", "--path", "/nonexistent-directory")
    assert code == EXIT_FAILED
    assert "is not a directory" in out
    assert "Traceback" not in out


def test_gitlab_target_fails_with_what_it_needs(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--forge", "gitlab", "--target", "group/project!1")
    assert code == EXIT_FAILED
    assert "not implemented yet" in out
    assert "--forge github" in out


def test_home_view_shows_state_before_help(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys)
    assert code == EXIT_OK
    lines = out.splitlines()
    assert lines[0].startswith("bin: ")  # §10 identify yourself
    assert "description: " in out
    assert "cache[" in out  # §8 live content, not a manual
    assert out.index("cache[") < out.index("help[")  # §9 next steps come last


def test_cache_status_lists_every_source(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "cache", "status")
    assert code == EXIT_OK
    assert "avm-terraform-resource-modules.csv" in out
    assert "terraform-to-arm-types.json" in out
    assert "azurerm-provider-schema.json" in out


def test_cache_rejects_an_unknown_action(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "cache", "wipe")
    assert code == EXIT_USAGE
    assert "valid actions: status, refresh" in out


def test_command_help_carries_flags_and_examples(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "review", "--help")
    assert code == EXIT_OK
    assert "flags[" in out
    assert "examples[3]:" in out  # §10 two or three worked examples
    assert "exit_codes[3]:" in out


def test_top_level_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, "--help")
    assert code == EXIT_OK
    assert "commands[3]{command,summary}:" in out


@pytest.mark.parametrize("flag", ["--version", "-v", "-V"])
def test_every_version_flag_prints_the_bare_version(
    capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    assert main([flag]) == EXIT_OK
    assert capsys.readouterr().out == f"{__version__}\n"


def test_version_answers_before_the_heavy_graph_loads() -> None:
    """§10: the fast path must not pull in the HCL parser or the provider graph."""
    probe = (
        "import sys;"
        "from iac_review.cli import main;"
        "main(['--version']);"
        "loaded=[m for m in ('hcl2','iac_review.providers','iac_review.forges')"
        " if m in sys.modules];"
        "sys.exit(1 if loaded else 0)"
    )
    assert subprocess.run([sys.executable, "-c", probe], check=False).returncode == 0


def test_svg_extension_writes_a_displayable_editable_artifact(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    import xml.etree.ElementTree as ET

    target = tmp_path / "platform.drawio.svg"
    code, out = _run(capsys, "review", "--path", str(FIXTURE), "--diagram", str(target))
    assert code == EXIT_OK
    root = ET.fromstring(target.read_text())
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert ET.fromstring(root.get("content") or "").tag == "mxfile"
    assert f"path: {target}" in out


def test_drawio_extension_still_writes_plain_xml(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "platform.drawio"
    _run(capsys, "review", "--path", str(FIXTURE), "--diagram", str(target))
    assert target.read_text().lstrip().startswith("<?xml")
    assert "<mxfile" in target.read_text()
