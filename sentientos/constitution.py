"""
SentientOS Constitutional Invariants.

Changes that violate sentientos.constitution are invalid by definition and must not be applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


DOMAIN_AUTHORITY = "authority"
DOMAIN_RECOVERY = "recovery"
DOMAIN_MEMORY = "memory"
DOMAIN_NARRATIVE = "narrative"
DOMAIN_EMBODIMENT = "embodiment"


@dataclass(frozen=True)
class Invariant:
    identifier: str
    domain: str
    statement: str


INVARIANTS: Sequence[Invariant] = (
    Invariant(
        identifier="AUTH-RECOVERY-LADDER-FINITE",
        domain=DOMAIN_AUTHORITY,
        statement="Recovery ladders are finite and non-recursive.",
    ),
    Invariant(
        identifier="AUTH-RECOVERY-ELIGIBILITY-PROOF-INTROSPECTION",
        domain=DOMAIN_AUTHORITY,
        statement="Recovery requires eligibility, proof, and introspection.",
    ),
    Invariant(
        identifier="AUTH-CONSENT-REQUIRED-EMBODIMENT-EGRESS",
        domain=DOMAIN_AUTHORITY,
        statement="Consent is required for all embodiment egress.",
    ),
    Invariant(
        identifier="AUTH-CONSENT-EXPLICIT-SCOPED-REVOCABLE-BOUNDED",
        domain=DOMAIN_AUTHORITY,
        statement="Consent is explicit, scoped, revocable, and time-bound.",
    ),
    Invariant(
        identifier="AUTH-NO-DEFAULT-APPROVALS",
        domain=DOMAIN_AUTHORITY,
        statement="No default or implicit approvals exist.",
    ),
    Invariant(
        identifier="REC-NEVER-RECOVER-IMMUTABLE",
        domain=DOMAIN_RECOVERY,
        statement="NEVER_RECOVER errors may never be recovered.",
    ),
    Invariant(
        identifier="REC-ONE-LADDER-PER-ERROR",
        domain=DOMAIN_RECOVERY,
        statement="At most one ladder exists per recoverable error.",
    ),
    Invariant(
        identifier="REC-RECOVERY-NO-RECOVERABLE-EMISSIONS",
        domain=DOMAIN_RECOVERY,
        statement="Recovery may not emit recoverable errors.",
    ),
    Invariant(
        identifier="REC-NO-RECOVER-TERMINAL",
        domain=DOMAIN_RECOVERY,
        statement="--no-recover is terminal.",
    ),
    Invariant(
        identifier="MEM-NO-SILENT-DELETION",
        domain=DOMAIN_MEMORY,
        statement="No silent deletion of memory.",
    ),
    Invariant(
        identifier="MEM-FORGETTING-SIMULATE-BEFORE-EXECUTE",
        domain=DOMAIN_MEMORY,
        statement="All forgetting must be simulated before execution.",
    ),
    Invariant(
        identifier="MEM-ECONOMICS-CONSTRAIN-RETENTION-NO-ERASE-WITHOUT-TRACE",
        domain=DOMAIN_MEMORY,
        statement="Memory economics constrain retention, never erase without trace.",
    ),
    Invariant(
        identifier="MEM-PRESSURE-ESCALATION-DETERMINISTIC-INSPECTABLE",
        domain=DOMAIN_MEMORY,
        statement="Pressure escalation is deterministic and inspectable.",
    ),
    Invariant(
        identifier="NARRATIVE-VIEWS-READ-ONLY",
        domain=DOMAIN_NARRATIVE,
        statement="Narrative views are read-only.",
    ),
    Invariant(
        identifier="NARRATIVE-RENDERING-NO-EVENTS",
        domain=DOMAIN_NARRATIVE,
        statement="Narrative rendering emits no events.",
    ),
    Invariant(
        identifier="NARRATIVE-INTROSPECTION-APPEND-ONLY",
        domain=DOMAIN_NARRATIVE,
        statement="Introspection events are append-only.",
    ),
    Invariant(
        identifier="NARRATIVE-ACTION-EMITS-INTROSPECTION",
        domain=DOMAIN_NARRATIVE,
        statement="Every meaningful action emits at least one introspection event.",
    ),
    Invariant(
        identifier="EMB-SIGNALS-PASS-CONTRACTS",
        domain=DOMAIN_EMBODIMENT,
        statement="All signals must pass contracts.",
    ),
    Invariant(
        identifier="EMB-SIGNALS-INCUR-MEMORY-COST",
        domain=DOMAIN_EMBODIMENT,
        statement="All signals incur memory-economic cost.",
    ),
    Invariant(
        identifier="EMB-SIMULATION-DEFAULT",
        domain=DOMAIN_EMBODIMENT,
        statement="Simulation-only is the default.",
    ),
    Invariant(
        identifier="EMB-NO-REAL-WORLD-IO-WITHOUT-ADAPTER",
        domain=DOMAIN_EMBODIMENT,
        statement="No real-world I/O without explicit future adapter enablement.",
    ),
)

INVARIANTS_BY_ID: Mapping[str, Invariant] = {inv.identifier: inv for inv in INVARIANTS}

INVARIANTS_BY_DOMAIN: Mapping[str, Sequence[str]] = {
    DOMAIN_AUTHORITY: (
        "AUTH-RECOVERY-LADDER-FINITE",
        "AUTH-RECOVERY-ELIGIBILITY-PROOF-INTROSPECTION",
        "AUTH-CONSENT-REQUIRED-EMBODIMENT-EGRESS",
        "AUTH-CONSENT-EXPLICIT-SCOPED-REVOCABLE-BOUNDED",
        "AUTH-NO-DEFAULT-APPROVALS",
    ),
    DOMAIN_RECOVERY: (
        "REC-NEVER-RECOVER-IMMUTABLE",
        "REC-ONE-LADDER-PER-ERROR",
        "REC-RECOVERY-NO-RECOVERABLE-EMISSIONS",
        "REC-NO-RECOVER-TERMINAL",
    ),
    DOMAIN_MEMORY: (
        "MEM-NO-SILENT-DELETION",
        "MEM-FORGETTING-SIMULATE-BEFORE-EXECUTE",
        "MEM-ECONOMICS-CONSTRAIN-RETENTION-NO-ERASE-WITHOUT-TRACE",
        "MEM-PRESSURE-ESCALATION-DETERMINISTIC-INSPECTABLE",
    ),
    DOMAIN_NARRATIVE: (
        "NARRATIVE-VIEWS-READ-ONLY",
        "NARRATIVE-RENDERING-NO-EVENTS",
        "NARRATIVE-INTROSPECTION-APPEND-ONLY",
        "NARRATIVE-ACTION-EMITS-INTROSPECTION",
    ),
    DOMAIN_EMBODIMENT: (
        "EMB-SIGNALS-PASS-CONTRACTS",
        "EMB-SIGNALS-INCUR-MEMORY-COST",
        "EMB-SIMULATION-DEFAULT",
        "EMB-NO-REAL-WORLD-IO-WITHOUT-ADAPTER",
    ),
}

CURRENT_SYSTEM_ASSERTIONS: Mapping[str, bool] = {inv.identifier: True for inv in INVARIANTS}
