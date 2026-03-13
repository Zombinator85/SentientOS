"""Unified federated hardening posture calibration.

This module centralizes shadow/advisory/enforce posture selection for the
federated hardening surfaces so runtime and operator views share one explicit,
auditable source.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_PROFILE_ENV = "SENTIENTOS_ENFORCEMENT_PROFILE"
_POLICY_PATH_ENV = "SENTIENTOS_ENFORCEMENT_POLICY_PATH"

_POSTURES = {"shadow", "advisory", "enforce"}


@dataclass(frozen=True)
class FederatedEnforcementPolicy:
    profile: str
    pulse_trust_epoch: str
    subject_fairness: str
    federated_quorum: str
    governance_digest: str
    repair_verification: str
    runtime_governor: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "source": self.source,
            "postures": {
                "pulse_trust_epoch": self.pulse_trust_epoch,
                "subject_fairness": self.subject_fairness,
                "federated_quorum": self.federated_quorum,
                "governance_digest": self.governance_digest,
                "repair_verification": self.repair_verification,
                "runtime_governor": self.runtime_governor,
            },
        }

    def posture_for(self, subsystem: str) -> str:
        mapping = self.to_dict()["postures"]
        if not isinstance(mapping, dict):
            return "shadow"
        value = mapping.get(subsystem)
        return value if isinstance(value, str) and value in _POSTURES else "shadow"


_PROFILE_BASELINES: dict[str, dict[str, str]] = {
    "local-dev-relaxed": {
        "pulse_trust_epoch": "shadow",
        "subject_fairness": "shadow",
        "federated_quorum": "shadow",
        "governance_digest": "shadow",
        "repair_verification": "shadow",
        "runtime_governor": "advisory",
    },
    "ci-advisory": {
        "pulse_trust_epoch": "advisory",
        "subject_fairness": "advisory",
        "federated_quorum": "advisory",
        "governance_digest": "advisory",
        "repair_verification": "advisory",
        "runtime_governor": "advisory",
    },
    "federation-enforce": {
        "pulse_trust_epoch": "enforce",
        "subject_fairness": "enforce",
        "federated_quorum": "enforce",
        "governance_digest": "enforce",
        "repair_verification": "enforce",
        "runtime_governor": "enforce",
    },
}


def _normalized_posture(value: object, fallback: str) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _POSTURES:
            return lowered
    return fallback


def _policy_file_overrides() -> tuple[dict[str, str], str]:
    path_value = os.getenv(_POLICY_PATH_ENV, "").strip()
    if not path_value:
        return ({}, "")
    path = Path(path_value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ({}, f"file:{path}:invalid")
    if not isinstance(payload, dict):
        return ({}, f"file:{path}:invalid")
    postures = payload.get("postures")
    if not isinstance(postures, dict):
        return ({}, f"file:{path}")
    overrides: dict[str, str] = {}
    for key, value in postures.items():
        if isinstance(key, str):
            normalized = _normalized_posture(value, "")
            if normalized:
                overrides[key] = normalized
    return (overrides, f"file:{path}")


def resolve_policy() -> FederatedEnforcementPolicy:
    profile = os.getenv(_PROFILE_ENV, "").strip().lower()
    source = "defaults"
    if profile in _PROFILE_BASELINES:
        selected = dict(_PROFILE_BASELINES[profile])
        source = f"profile:{profile}"
    else:
        legacy_mode = _normalized_posture(os.getenv("SENTIENTOS_GOVERNOR_MODE", "shadow"), "shadow")
        selected = {
            "pulse_trust_epoch": legacy_mode,
            "subject_fairness": legacy_mode,
            "federated_quorum": legacy_mode,
            "governance_digest": legacy_mode,
            "repair_verification": legacy_mode,
            "runtime_governor": legacy_mode,
        }
        profile = "legacy-governor-mode"
        source = "legacy-governor-mode"

    file_overrides, file_source = _policy_file_overrides()
    if file_overrides:
        selected.update(file_overrides)
        source = f"{source}+{file_source}" if file_source else source

    env_map = {
        "pulse_trust_epoch": "SENTIENTOS_ENFORCEMENT_PULSE_TRUST_EPOCH",
        "subject_fairness": "SENTIENTOS_ENFORCEMENT_SUBJECT_FAIRNESS",
        "federated_quorum": "SENTIENTOS_ENFORCEMENT_FEDERATED_QUORUM",
        "governance_digest": "SENTIENTOS_ENFORCEMENT_GOVERNANCE_DIGEST",
        "repair_verification": "SENTIENTOS_ENFORCEMENT_REPAIR_VERIFICATION",
        "runtime_governor": "SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR",
    }
    for key, envvar in env_map.items():
        selected[key] = _normalized_posture(os.getenv(envvar), selected[key])

    return FederatedEnforcementPolicy(
        profile=profile,
        pulse_trust_epoch=selected["pulse_trust_epoch"],
        subject_fairness=selected["subject_fairness"],
        federated_quorum=selected["federated_quorum"],
        governance_digest=selected["governance_digest"],
        repair_verification=selected["repair_verification"],
        runtime_governor=selected["runtime_governor"],
        source=source,
    )


def write_policy_snapshot(path: Path) -> dict[str, object]:
    payload = {"schema_version": 1, **resolve_policy().to_dict()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload

