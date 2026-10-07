from __future__ import annotations

import json
from pathlib import Path

from scripts.analyze_test_failures import _extract_failures, generate_failure_digest


def _write_fixture(path: Path) -> None:
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<testsuites>
  <testsuite name=\"pytest\" tests=\"4\" failures=\"4\" errors=\"0\">
    <testcase classname=\"tests.test_beta\" name=\"test_b\" file=\"tests/test_beta.py\" line=\"10\">
      <failure type=\"AssertionError\" message=\"expected 1 == 2&#10;line two&#10;line three&#10;line four\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_alpha\" name=\"test_a\" file=\"tests/test_alpha.py\" line=\"3\">
      <failure type=\"ValueError\" message=\"bad value&#10;context&#10;extra&#10;ignored\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_beta\" name=\"test_b\" file=\"tests/test_beta.py\" line=\"10\">
      <failure type=\"AssertionError\" message=\"expected 1 == 2&#10;line two&#10;line three&#10;line four\">traceback omitted</failure>
    </testcase>
    <testcase classname=\"tests.test_gamma\" name=\"test_c\" file=\"tests/test_gamma.py\" line=\"8\">
      <error type=\"RuntimeError\" message=\"boom&#10;second&#10;third&#10;fourth\">traceback omitted</error>
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


def test_failure_parser_can_preserve_full_message_for_causal_identity(tmp_path):
    junitxml = tmp_path / "report.xml"
    _write_fixture(junitxml)

    failures = _extract_failures(junitxml, max_message_lines=None)

    assert failures[0].message_lines == (
        "expected 1 == 2",
        "line two",
        "line three",
        "line four",
    )


def test_failure_identity_uses_message_beyond_display_excerpt(tmp_path):
    junitxml = tmp_path / "report.xml"
    junitxml.write_text(
        """<testsuites><testsuite tests="2" failures="2">
        <testcase classname="tests.test_alpha" name="test_a">
          <failure type="AssertionError" message="first&#10;second&#10;third&#10;detail A" />
        </testcase>
        <testcase classname="tests.test_alpha" name="test_a">
          <failure type="AssertionError" message="first&#10;second&#10;third&#10;detail B" />
        </testcase>
        </testsuite></testsuites>""",
        encoding="utf-8",
    )

    payload = generate_failure_digest(
        junitxml_path=junitxml,
        output_path=tmp_path / "digest.json",
        run_provenance_hash="hash123",
        max_message_lines=3,
    )

    groups = payload["failure_groups"]
    assert len(groups) == 2
    assert {group["short_message"] for group in groups} == {"first\nsecond\nthird"}
    assert len({group["semantic_signature"] for group in groups}) == 2


def test_semantic_failure_signature_does_not_include_testcase_line(tmp_path):
    left = tmp_path / "left.xml"
    right = tmp_path / "right.xml"
    body = '<?xml version="1.0"?><testsuites><testsuite tests="1" failures="1"><testcase classname="tests.test_x" name="test_x" file="tests/test_x.py" line="{}"><failure type="AssertionError" message="expected 1">trace</failure></testcase></testsuite></testsuites>'
    left.write_text(body.format(10), encoding="utf-8")
    right.write_text(body.format(99), encoding="utf-8")
    a = generate_failure_digest(junitxml_path=left, output_path=tmp_path / "a.json", run_provenance_hash="a")
    b = generate_failure_digest(junitxml_path=right, output_path=tmp_path / "b.json", run_provenance_hash="b")
    assert a["failure_groups"][0]["semantic_signature"] == b["failure_groups"][0]["semantic_signature"]
    assert a["failure_groups"][0]["line"] != b["failure_groups"][0]["line"]
