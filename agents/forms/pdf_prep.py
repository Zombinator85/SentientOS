"""Stage-5 SSA-827 PDF prefill utility.

This module fills non-signature claimant details into an SSA-827 template
entirely in memory. It never writes to disk and exposes a redacted preview
suitable for logs.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from pdfrw import PdfDict, PdfReader, PdfWriter


ALLOWED_FIELDS = {
    "claimant_name",
    "dob",
    "phone",
    "email",
    "address",
    "providers",
    "conditions",
}


def redact(value: str) -> str:
    """Return a deterministic redaction marker for non-empty strings."""

    if isinstance(value, str) and value:
        return "***"
    return ""


class SSA827Prefill:
    """Prepare an SSA-827 PDF with claimant information only."""

    def __init__(self, profile: dict, approved: bool):
        self.profile = profile
        self.approved = approved
        self.template_path = Path(__file__).resolve().parents[2] / "resources" / "ssa_827_blank.pdf"

    def require_approval(self):
        return self.approved

    def prefill_pdf(self) -> Dict[str, Any]:
        if not self.approved:
            return {"status": "approval_required"}

        pdf = self._load_pdf()
        fields = list(self._get_form_fields(pdf))
        prefill_data, raw_values = self._build_prefill_data()
        self._apply_fields(fields, prefill_data)

        pdf_bytes = self._to_bytes(pdf)
        preview = self._build_redacted_preview(raw_values)

        return {"status": "prefill_complete", "bytes": pdf_bytes, "redacted_preview": preview}

    def _load_pdf(self):
        return PdfReader(str(self.template_path))

    def _get_form_fields(self, pdf) -> Iterable[PdfDict]:
        root = getattr(pdf, "Root", None)
        if not root:
            return []
        acro_form = getattr(root, "AcroForm", None)
        if not acro_form:
            return []
        fields = getattr(acro_form, "Fields", None)
        if not fields:
            return []
        return fields

    def _apply_fields(self, fields: Iterable[PdfDict], prefill_data: Dict[str, str]) -> None:
        for field in fields:
            name = self._get_field_name(field)
            if name and name in prefill_data:
                value = prefill_data[name]
                field.update(PdfDict(V=value, AS=value))

    def _get_field_name(self, field: PdfDict) -> str | None:
        raw_name = field.get("T") or field.get("/T") or getattr(field, "T", None)
        if raw_name is None:
            return None
        name = str(raw_name).strip("()")
        return name.lstrip("/")

    def _build_prefill_data(self) -> Tuple[Dict[str, str], Dict[str, Any]]:
        data: Dict[str, str] = {}
        raw_values: Dict[str, Any] = {}

        for key in ALLOWED_FIELDS:
            value = self._find_profile_value(key)
            if value is None:
                continue

            normalized = self._normalize_value(value)
            if normalized:
                data[key] = normalized
                raw_values[key] = value

        return data, raw_values

    def _normalize_value(self, value: Any) -> str:
        if isinstance(value, list):
            normalized_items = [str(item) for item in value if str(item)]
            return "; ".join(normalized_items)
        if isinstance(value, dict):
            parts = [f"{k}: {v}" for k, v in value.items() if v not in (None, "")]
            return "; ".join(parts)
        return str(value) if str(value) else ""

    def _build_redacted_preview(self, raw_values: Dict[str, Any]) -> Dict[str, Any]:
        preview: Dict[str, Any] = {}
        for key, value in raw_values.items():
            preview[key] = self._redact_value(value)
        return preview

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [redact(str(item)) for item in value]
        if isinstance(value, dict):
            return {k: redact(str(v)) for k, v in value.items()}
        return redact(str(value))

    def _find_profile_value(self, key: str) -> Any:
        def _search(node: Any) -> Any:
            if isinstance(node, dict):
                if key in node:
                    return node[key]
                for value in node.values():
                    found = _search(value)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = _search(item)
                    if found is not None:
                        return found
            return None

        return _search(self.profile)

    def _to_bytes(self, pdf) -> bytes:
        buffer = BytesIO()
        PdfWriter().write(buffer, pdf)
        return buffer.getvalue()
