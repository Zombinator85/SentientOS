from __future__ import annotations

import pytest

from sentientos import bounded_jurisprudence
from sentientos.jurisprudence_consumption import build_jurisprudence_consumption_summary

pytestmark = pytest.mark.no_legacy_skip


def test_unmapped_decision_classes_have_no_authoritative_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bounded_jurisprudence, "EXPLICIT_AUTHORITY_RULES", [])

    summary = build_jurisprudence_consumption_summary(consumer_surface="test")

    assert all(row["authoritative_surface"] is None for row in summary["emitted_vs_consumed"])
