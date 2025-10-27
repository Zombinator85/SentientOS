"""Proof-of-Validity engine for covenant amendment verification."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import copy

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - fallback path
    yaml = None  # type: ignore[assignment]


@dataclass(slots=True)
class ProofReport:
    """Machine-consumable verdict emitted by :class:`ProofVerifier`."""

    valid: bool
    violations: List[Dict[str, Any]]
    trace: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the report."""

        return {
            "valid": bool(self.valid),
            "violations": [copy.deepcopy(item) for item in self.violations],
            "trace": [copy.deepcopy(item) for item in self.trace],
        }

    def summary(self) -> str:
        """Create a short textual summary useful for narration."""

        total = len(self.trace)
        failures = len(self.violations)
        passed = max(total - failures, 0)
        status = "VALID" if self.valid else "QUARANTINED"
        return (
            f"Amendment validated: {passed} invariants passed, "
            f"{failures} violations detected, status = {status}."
        )


class ProofVerifier:
    """Simple SMT-like verifier that evaluates covenant invariants."""

    DEFAULT_REQUIRED_FIELDS: Sequence[str] = (
        "objective",
        "directives",
        "testing_requirements",
    )
    DEFAULT_FORBIDDEN_STATUSES: Sequence[str] = (
        "reboot",
        "retired",
        "nullified",
        "decommissioned",
    )

    def __init__(
        self,
        invariants_path: str | Path | None = None,
        *,
        required_fields: Sequence[str] | None = None,
        forbidden_statuses: Sequence[str] | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        default_path = base_dir / "vow" / "invariants.yaml"
        self._invariants_path = Path(invariants_path or default_path)
        self._required_fields = tuple(
            dict.fromkeys(required_fields or self.DEFAULT_REQUIRED_FIELDS)
        )
        self._forbidden_statuses = {
            str(status).strip().lower()
            for status in (forbidden_statuses or self.DEFAULT_FORBIDDEN_STATUSES)
        }
        self._invariants_cache: List[Dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Public API
    def evaluate(self, proposal: Mapping[str, Any] | Any) -> ProofReport:
        """Evaluate *proposal* against all configured invariants."""

        invariants = self._load_invariants()
        payload = self._normalise_payload(proposal)
        trace: List[Dict[str, Any]] = []
        violations: List[Dict[str, Any]] = []

        for entry in invariants:
            name = str(entry.get("name", "invariant"))
            rule = str(entry.get("rule", ""))
            description = str(entry.get("description", ""))
            severity = entry.get("severity")
            hint = entry.get("proof_hint")
            result, context, detail = self._evaluate_invariant(name, payload)
            trace.append(
                {
                    "invariant": name,
                    "rule": rule,
                    "passed": result,
                    "context": context,
                }
            )
            if result:
                continue
            violation: Dict[str, Any] = {
                "invariant": name,
                "rule": rule,
                "detail": detail,
            }
            if description:
                violation["description"] = description
            if severity:
                violation["severity"] = severity
            if hint:
                violation["proof_hint"] = hint
            violations.append(violation)

        return ProofReport(valid=not violations, violations=violations, trace=trace)

    def describe_invariants(self) -> List[Dict[str, Any]]:
        """Return the static invariant catalogue."""

        return [copy.deepcopy(entry) for entry in self._load_invariants()]

    # ------------------------------------------------------------------
    # Internal helpers
    def _load_invariants(self) -> List[Dict[str, Any]]:
        if self._invariants_cache is not None:
            return self._invariants_cache
        try:
            raw = self._invariants_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._invariants_cache = []
            return []
        data: Mapping[str, Any] | None = None
        if yaml is not None:
            try:
                loaded = yaml.safe_load(raw)
            except Exception:  # pragma: no cover - fallback to manual parser
                loaded = None
            if isinstance(loaded, Mapping):
                data = loaded  # type: ignore[assignment]
        if data is None or "invariants" not in data:
            data = self._fallback_yaml_load(raw)
        invariants = data.get("invariants", []) if isinstance(data, Mapping) else []
        normalised: List[Dict[str, Any]] = []
        for entry in invariants:
            if isinstance(entry, Mapping):
                normalised.append(dict(entry))
        self._invariants_cache = normalised
        return normalised

    def _normalise_payload(
        self, proposal: Mapping[str, Any] | Any
    ) -> Dict[str, Any]:
        if hasattr(proposal, "to_dict"):
            try:
                base: Mapping[str, Any] = proposal.to_dict()
            except Exception:  # pragma: no cover - defensive
                base = {}
        elif isinstance(proposal, Mapping):
            base = proposal
        else:
            base = {}

        payload: Dict[str, Any] = dict(base)
        proposed = self._ensure_mapping(
            payload.get("proposed_spec") or payload.get("spec") or {}
        )
        original = self._ensure_mapping(payload.get("original_spec") or {})
        ledger_diff = self._ensure_mapping(payload.get("ledger_diff") or {})

        required = payload.get("required_fields")
        if not isinstance(required, Iterable) or isinstance(required, (str, bytes)):
            required_set = set(self._required_fields)
        else:
            required_set = {str(item) for item in required}
        spec_fields = set(proposed)
        status = str(proposed.get("status", payload.get("status", "")))
        status_normalised = status.strip().lower()
        recursion_break = bool(
            payload.get("recursion_break")
            or proposed.get("recursion_break")
            or str(proposed.get("recursion", "")).strip().lower() in {"break", "halt"}
        )

        payload.update(
            {
                "spec": proposed,
                "original_spec": original,
                "ledger_diff": ledger_diff,
                "required_fields": sorted(required_set),
                "spec_fields": sorted(spec_fields),
                "status": status,
                "status_normalised": status_normalised,
                "recursion_break": recursion_break,
            }
        )
        return payload

    def _ensure_mapping(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    def _fallback_yaml_load(self, raw: str) -> Dict[str, Any]:
        invariants: List[Dict[str, Any]] = []
        current: Dict[str, Any] | None = None
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("invariants"):
                continue
            if stripped.startswith("-"):
                if current:
                    invariants.append(current)
                current = {}
                stripped = stripped[1:].strip()
                if stripped:
                    key, _, value = stripped.partition(":")
                    current[key.strip()] = self._coerce_value(value)
                continue
            if current is None:
                continue
            key, _, value = stripped.partition(":")
            if not key:
                continue
            current[key.strip()] = self._coerce_value(value)
        if current:
            invariants.append(current)
        return {"invariants": invariants}

    @staticmethod
    def _coerce_value(value: str) -> Any:
        text = value.strip()
        if text.startswith("\"") and text.endswith("\""):
            text = text[1:-1]
        return text

    def _evaluate_invariant(
        self, name: str, payload: Mapping[str, Any]
    ) -> tuple[bool, Dict[str, Any], str | None]:
        if name == "structural_integrity":
            return self._check_structural_integrity(payload)
        if name == "audit_continuity":
            return self._check_audit_continuity(payload)
        if name == "forbidden_status":
            return self._check_forbidden_status(payload)
        if name == "recursion_guard":
            return self._check_recursion_guard(payload)
        # Unknown invariants are considered informational but passing.
        return True, {}, None

    def _check_structural_integrity(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, Dict[str, Any], str | None]:
        required = set(payload.get("required_fields", []))
        spec_fields = set(payload.get("spec_fields", []))
        missing = sorted(required - spec_fields)
        passed = not missing
        detail = None
        if not passed:
            detail = f"Missing required fields: {', '.join(missing)}"
        context = {
            "required_fields": sorted(required),
            "spec_fields": sorted(spec_fields),
            "missing": missing,
        }
        return passed, context, detail

    def _check_audit_continuity(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, Dict[str, Any], str | None]:
        ledger_diff = self._ensure_mapping(payload.get("ledger_diff"))
        removed = ledger_diff.get("removed", [])
        if isinstance(removed, Sequence) and not isinstance(removed, (str, bytes)):
            removed_list = list(removed)
        elif removed is None:
            removed_list = []
        else:
            removed_list = [removed]
        passed = not removed_list
        detail = None if passed else "Ledger entries were removed"
        context = {"removed": removed_list}
        return passed, context, detail

    def _check_forbidden_status(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, Dict[str, Any], str | None]:
        status = str(payload.get("status", ""))
        status_normalised = str(payload.get("status_normalised", "")).strip().lower()
        forbidden = status_normalised in self._forbidden_statuses
        passed = not forbidden
        detail = None if passed else f"Status '{status}' violates forbidden list"
        context = {
            "status": status,
            "forbidden_statuses": sorted(self._forbidden_statuses),
        }
        return passed, context, detail

    def _check_recursion_guard(
        self, payload: Mapping[str, Any]
    ) -> tuple[bool, Dict[str, Any], str | None]:
        recursion_break = bool(payload.get("recursion_break", False))
        passed = not recursion_break
        detail = None if passed else "Recursion break flag detected"
        context = {"recursion_break": recursion_break}
        return passed, context, detail


__all__ = ["ProofVerifier", "ProofReport"]
