from __future__ import annotations

import json
from pathlib import Path

from scripts.analyze_test_failures import generate_failure_digest


def _write_fixture(path: Path) -> None:
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<testsuites>
  <testsuite name=\"pytest\" tests=\"4\" failures=\"4\" errors=\"0\">
    <testcase classname=\"tests.test_beta\" name=\"test_b\" file=\"tests/test_beta.py\" line=\"10\">
      <failure type=\"AssertionError\" message=\"expected 1 == 2\nline two\nline three\nline four\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_alpha\" name=\"test_a\" file=\"tests/test_alpha.py\" line=\"3\">
      <failure type=\"ValueError\" message=\"bad value\ncontext\nextra\nignored\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_beta\" name=\"test_b\" file=\"tests/test_beta.py\" line=\"10\">
      <failure type=\"AssertionError\" message=\"expected 1 == 2\nline two\nline three\nline four\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_gamma\" name=\"test_c\" file=\"tests/test_gamma.py\" line=\"8\">
      <error type=\"RuntimeError\" message=\"boom\nsecond\nthird\nfourth\">traceback omitted</error>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )


def test_generate_failure_digest_groups_and_sorts_stably(tmp_path):
    junitxml = tmp_path / "report.xml"
    digest_path = tmp_path / "digest.json"
    _write_fixture(junitxml)

    payload = generate_failure_digest(
        junitxml_path=junitxml,
        output_path=digest_path,
        run_provenance_hash="hash123",
        max_message_lines=3,
    )

    assert payload["schema_version"] == 1
    assert payload["run_provenance_hash"] == "hash123"
    groups = payload["failure_groups"]
    assert [group["count"] for group in groups] == [2, 1, 1]
    assert groups[0]["example_nodeid"] == "tests.test_beta::test_b"
    assert groups[0]["short_message"] == "expected 1 == 2\nline two\nline three"
    assert groups[0]["rerun_command"] == "python -m scripts.run_tests -q tests.test_beta::test_b"

    assert [group["example_nodeid"] for group in groups[1:]] == [
        "tests.test_alpha::test_a",
        "tests.test_gamma::test_c",
    ]


def test_generate_failure_digest_is_deterministic(tmp_path):
    junitxml = tmp_path / "report.xml"
    _write_fixture(junitxml)

    digest_a = tmp_path / "digest_a.json"
    digest_b = tmp_path / "digest_b.json"

    payload_a = generate_failure_digest(
        junitxml_path=junitxml,
        output_path=digest_a,
        run_provenance_hash="samehash",
        max_message_lines=3,
    )
    payload_b = generate_failure_digest(
        junitxml_path=junitxml,
        output_path=digest_b,
        run_provenance_hash="samehash",
        max_message_lines=3,
    )

    assert payload_a == payload_b
    assert json.loads(digest_a.read_text(encoding="utf-8")) == json.loads(digest_b.read_text(encoding="utf-8"))
