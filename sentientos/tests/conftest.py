"""Local test fixtures for sentientos package tests."""
from __future__ import annotations

import builtins
import json
import sys
import types
from pathlib import Path

# Ensure repository root is available on the import path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Stub privilege checks and optional modules to keep imports lightweight
builtins.require_admin_banner = lambda *a, **k: None  # type: ignore[attr-defined]
builtins.require_covenant_alignment = lambda *a, **k: None  # type: ignore[attr-defined]

try:
    import yaml  # type: ignore # noqa: F401
except Exception:  # pragma: no cover - optional dependency shim
    yaml_stub = types.ModuleType("yaml")

    def _safe_load(text: str | None, *_, **__) -> object:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    yaml_stub.safe_load = _safe_load  # type: ignore[attr-defined]
    sys.modules["yaml"] = yaml_stub

# Stub agents modules required during sentientos package import
agents_module = types.ModuleType("agents")
forms_module = types.ModuleType("agents.forms")
pdf_prep_module = types.ModuleType("agents.forms.pdf_prep")
pdf_prep_module.SSA827Prefill = object  # type: ignore[attr-defined]
ssa_module = types.ModuleType("agents.forms.ssa_disability_agent")
ssa_module.SSADisabilityAgent = lambda profile=None: None  # type: ignore[attr-defined]
forms_module.ssa_disability_agent = ssa_module  # type: ignore[attr-defined]
forms_module.pdf_prep = pdf_prep_module  # type: ignore[attr-defined]

sys.modules.setdefault("agents", agents_module)
sys.modules.setdefault("agents.forms", forms_module)
sys.modules.setdefault("agents.forms.pdf_prep", pdf_prep_module)
sys.modules.setdefault("agents.forms.ssa_disability_agent", ssa_module)

pdfrw_stub = types.SimpleNamespace(PdfDict=dict, PdfReader=lambda *a, **k: None, PdfWriter=lambda *a, **k: None)
sys.modules.setdefault("pdfrw", pdfrw_stub)
