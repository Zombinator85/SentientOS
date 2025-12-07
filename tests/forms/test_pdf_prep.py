import pytest
from pdfrw import PdfDict

from agents.forms.pdf_prep import ALLOWED_FIELDS, SSA827Prefill, redact


pytestmark = pytest.mark.no_legacy_skip


def build_pdf_stub(field_names):
    fields = [PdfDict(T=name) for name in field_names]
    return PdfDict(Root=PdfDict(AcroForm=PdfDict(Fields=fields)))


def test_prefill_requires_explicit_approval():
    profile = {"claimant_name": "Ada Lovelace"}
    prefill = SSA827Prefill(profile, approved=False)

    result = prefill.prefill_pdf()

    assert result == {"status": "approval_required"}


def test_prefill_returns_pdf_bytes(monkeypatch):
    profile = {
        "claimant_name": "Ada Lovelace",
        "dob": "1815-12-10",
        "contact": {"phone": "555-0100", "email": "ada@example.com"},
        "providers": ["Clinic A", "Clinic B"],
        "conditions": ["mobility", "vision"],
    }

    loaded_pdfs = []

    def fake_load(self):
        pdf = build_pdf_stub(list(ALLOWED_FIELDS) + ["signature"])
        loaded_pdfs.append(pdf)
        return pdf

    monkeypatch.setattr(SSA827Prefill, "_load_pdf", fake_load)

    prefill = SSA827Prefill(profile, approved=True)

    result = prefill.prefill_pdf()

    assert result["status"] == "prefill_complete"
    assert isinstance(result["bytes"], (bytes, bytearray))
    assert len(result["bytes"]) > 0

    preview = result["redacted_preview"]
    assert preview["claimant_name"] == "***"
    assert preview["dob"] == "***"
    assert preview["phone"] == "***"
    assert preview["email"] == "***"
    assert preview["providers"] == ["***", "***"]
    assert preview["conditions"] == ["***", "***"]
    assert "signature" not in preview

    filled_pdf = loaded_pdfs[0]
    field_lookup = {str(getattr(field, "T", "")).strip("()"): field for field in filled_pdf.Root.AcroForm.Fields}
    assert getattr(field_lookup["claimant_name"], "V") == "Ada Lovelace"
    assert getattr(field_lookup["dob"], "V") == "1815-12-10"
    assert getattr(field_lookup["providers"], "V") == "Clinic A; Clinic B"
    assert getattr(field_lookup["conditions"], "V") == "mobility; vision"
    assert getattr(field_lookup["signature"], "V", None) is None


def test_redact_helper():
    assert redact("") == ""
    assert redact("value") == "***"
