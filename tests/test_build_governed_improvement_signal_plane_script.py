import json
from pathlib import Path
from scripts.build_governed_improvement_signal_plane import main


def test_cli_build_validate_and_markdown(tmp_path):
    out = tmp_path / "out.json"; md = tmp_path / "out.md"
    rc = main(["build", "--input", "tests/fixtures/governed_improvement_signal_plane/mixed.json", "--json-output", str(out), "--markdown-output", str(md)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["schema"] == "governed_improvement_signal_plane_evaluation:v1"
    assert main(["validate", str(out)]) == 0
    assert "Governed Improvement" in md.read_text()


def test_cli_blocked_returns_nonzero(tmp_path):
    out = tmp_path / "bad.json"
    rc = main(["build", "--input", "tests/fixtures/governed_improvement_signal_plane/bad_authority.json", "--json-output", str(out)])
    assert rc == 2


def test_cli_inspect_fixtures(capsys):
    assert main(["inspect-fixtures"]) == 0
    assert "mixed.json" in capsys.readouterr().out
