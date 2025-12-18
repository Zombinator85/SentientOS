import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "lint_glossary.py"
REPORT = ROOT / "lint" / "semantic_violations.jsonl"


def test_glossary_lint_runs_clean() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    violations = []
    if REPORT.exists():
        with REPORT.open(encoding="utf-8") as report_file:
            for line in report_file:
                line = line.strip()
                if line:
                    violations.append(json.loads(line))

    if result.returncode != 0 or violations:
        details = [
            f"Glossary lint found violations. Report: {REPORT}",
            f"Return code: {result.returncode}",
        ]
        if violations:
            sample = json.dumps(violations[0])
            details.append(f"Sample violation: {sample}")
        details.append(f"stdout:\n{result.stdout}")
        details.append(f"stderr:\n{result.stderr}")
        raise AssertionError("\n".join(details))
