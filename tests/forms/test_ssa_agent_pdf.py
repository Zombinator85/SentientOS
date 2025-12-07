import pytest
from pdfrw import PdfDict

from agents.forms.ssa_disability_agent import SSADisabilityAgent
from agents.forms.pdf_prep import ALLOWED_FIELDS, SSA827Prefill


pytestmark = pytest.mark.no_legacy_skip


def build_pdf_stub():
    fields = [PdfDict(T=name) for name in ALLOWED_FIELDS]
    return PdfDict(Root=PdfDict(AcroForm=PdfDict(Fields=fields)))


def test_prefill_ssa_827_enforces_approval(monkeypatch):
    monkeypatch.setattr("agents.forms.ssa_disability_agent.load_selectors", lambda *_: {})
    agent = SSADisabilityAgent(profile={"claimant_name": "Test"})

    result = agent.prefill_ssa_827(approval_flag=False)

    assert result == {"status": "approval_required"}


def test_prefill_ssa_827_is_deterministic(monkeypatch):
    profile = {
        "claimant_name": "Ada Lovelace",
        "dob": "1815-12-10",
        "conditions": ["mobility", "vision"],
    }
    monkeypatch.setattr("agents.forms.ssa_disability_agent.load_selectors", lambda *_: {})
    agent = SSADisabilityAgent(profile=profile)

    def fake_load(self):
        return build_pdf_stub()

    monkeypatch.setattr(SSA827Prefill, "_load_pdf", fake_load)

    first = agent.prefill_ssa_827(approval_flag=True)
    second = agent.prefill_ssa_827(approval_flag=True)

    assert first["status"] == "prefill_complete"
    assert first["bytes"] == second["bytes"]
    assert first["redacted_preview"] == second["redacted_preview"]
