from __future__ import annotations

from pathlib import Path

import pytest

import sentientos.operator_report_attestation as attestation


@pytest.mark.no_legacy_skip
def test_malformed_operator_report_schema_version_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_ENFORCE", "1")
    monkeypatch.setattr(
        attestation,
        "resolve_recent_rows",
        lambda **_kwargs: [{"schema_version": {"unexpected": "object"}}],
    )
    monkeypatch.setattr(
        attestation,
        "_resolve_signer",
        lambda **_kwargs: {"mode": "hmac-test", "secret": "test"},
    )

    result = attestation.verify_recent_operator_reports(tmp_path)

    assert result.ok is False
    assert result.status == "fail"
    assert result.reason == "schema_version_invalid"
    assert result.checked_n == 0


@pytest.mark.no_legacy_skip
def test_operator_report_schema_version_defaults_for_legacy_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_ENFORCE", "1")
    monkeypatch.setattr(
        attestation,
        "resolve_recent_rows",
        lambda **_kwargs: [{"schema_version": None}],
    )
    monkeypatch.setattr(
        attestation,
        "_resolve_signer",
        lambda **_kwargs: {"mode": "hmac-test", "secret": "test"},
    )

    result = attestation.verify_recent_operator_reports(tmp_path)

    assert result.ok is False
    assert result.reason != "schema_version_invalid"


@pytest.mark.no_legacy_skip
def test_boolean_operator_report_schema_version_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_VERIFY", "1")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_ENFORCE", "1")
    monkeypatch.setattr(
        attestation,
        "resolve_recent_rows",
        lambda **_kwargs: [{"schema_version": True}],
    )
    monkeypatch.setattr(
        attestation,
        "_resolve_signer",
        lambda **_kwargs: {"mode": "hmac-test", "secret": "test"},
    )

    result = attestation.verify_recent_operator_reports(tmp_path)

    assert result.ok is False
    assert result.reason == "schema_version_invalid"
