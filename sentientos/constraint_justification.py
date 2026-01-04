"""Read-only constraint justification catalog.

Justification is attribution-only: it explains why constraints exist without
granting permission, changing execution, or automating decisions. Review signals
are informational and must never be treated as enforcement outcomes. Constraints
must still justify continued existence, but justification never becomes a
permission path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Mapping

from policy_digest import policy_digest_reference


@dataclass(frozen=True, slots=True)
class DoctrineReference:
    """Stable policy reference for constraint attribution."""

    policy_id: str
    policy_hash: str

    def canonical_payload(self) -> dict[str, str]:
        return {
            "policy_id": self.policy_id,
            "policy_hash": self.policy_hash,
        }


@dataclass(frozen=True, slots=True)
class ConstraintJustification:
    """Immutable, non-authoritative constraint justification metadata."""

    constraint_id: str
    constraint_scope: str
    doctrine_reference: DoctrineReference
    justification_text: str
    review_epoch: int
    status: str

    def canonical_payload(self) -> dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "constraint_scope": self.constraint_scope,
            "doctrine_reference": self.doctrine_reference.canonical_payload(),
            "justification_text": self.justification_text,
            "review_epoch": self.review_epoch,
            "status": self.status,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def stable_hash(self) -> str:
        """Deterministic hash for attribution and audit trails."""

        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def __hash__(self) -> int:
        return int(self.stable_hash(), 16)


def _doctrine_reference() -> DoctrineReference:
    reference = policy_digest_reference()
    return DoctrineReference(
        policy_id=reference["policy_id"],
        policy_hash=reference["policy_hash"],
    )


_DOCTRINE_REFERENCE = _doctrine_reference()


_CONSTRAINT_JUSTIFICATIONS: dict[str, ConstraintJustification] = {
    "runtime::load-homeostasis": ConstraintJustification(
        constraint_id="runtime::load-homeostasis",
        constraint_scope="runtime",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Runtime load homeostasis prevents runaway pressure without revoking presence.",
        review_epoch=3,
        status="active",
    ),
    "autonomy::browser::open": ConstraintJustification(
        constraint_id="autonomy::browser::open",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Browser opens remain auditable and bound to declared autonomy controls.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::browser::click": ConstraintJustification(
        constraint_id="autonomy::browser::click",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Browser clicks require traceable autonomy constraints and council visibility.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::browser::type": ConstraintJustification(
        constraint_id="autonomy::browser::type",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Browser typing is constrained to prevent unreviewed public posting.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::browser::post": ConstraintJustification(
        constraint_id="autonomy::browser::post",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Browser posting remains quorum-gated and reviewable for accountability.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::gui::click": ConstraintJustification(
        constraint_id="autonomy::gui::click",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="GUI clicks stay bounded to audited, explainable control flows.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::gui::move": ConstraintJustification(
        constraint_id="autonomy::gui::move",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="GUI movement remains safety-scoped and panic-aware without implicit permission.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::gui::type": ConstraintJustification(
        constraint_id="autonomy::gui::type",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="GUI typing is constrained to protect sensitive inputs and audit trails.",
        review_epoch=2,
        status="active",
    ),
    "autonomy::gui::focus": ConstraintJustification(
        constraint_id="autonomy::gui::focus",
        constraint_scope="tooling",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="GUI focus shifts are logged to preserve operator accountability.",
        review_epoch=2,
        status="active",
    ),
    "epr::irreversible-external-effects": ConstraintJustification(
        constraint_id="epr::irreversible-external-effects",
        constraint_scope="startup",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="EPR blocks irreversible external effects during bootstrap to keep entrypoints reversible.",
        review_epoch=4,
        status="active",
    ),
    "volatility::capability-scope": ConstraintJustification(
        constraint_id="volatility::capability-scope",
        constraint_scope="volatility",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Volatility routing narrows capabilities without revoking presence or consent signals.",
        review_epoch=4,
        status="active",
    ),
    "cathedral::quarantine-classification": ConstraintJustification(
        constraint_id="cathedral::quarantine-classification",
        constraint_scope="runtime",
        doctrine_reference=_DOCTRINE_REFERENCE,
        justification_text="Failures classify into quarantine to preserve auditability before rejection.",
        review_epoch=4,
        status="active",
    ),
}


def constraint_justification_catalog() -> dict[str, ConstraintJustification]:
    """Return a copy of the constraint justification catalog."""

    return dict(_CONSTRAINT_JUSTIFICATIONS)


def get_constraint_justification(constraint_id: str) -> ConstraintJustification | None:
    """Return the justification for a constraint identifier, if known."""

    return _CONSTRAINT_JUSTIFICATIONS.get(constraint_id)


def enumerate_constraint_review_signals(
    constraint_ids: Iterable[str],
    *,
    justifications: Mapping[str, ConstraintJustification] | None = None,
    current_epoch: int,
    review_window: int = 0,
) -> list[dict[str, object]]:
    """Enumerate review signals; signals are informational, not enforcement."""

    if review_window < 0:
        raise ValueError("review_window must be non-negative")
    catalog = justifications or _CONSTRAINT_JUSTIFICATIONS
    signals: list[dict[str, object]] = []
    for constraint_id in sorted(set(constraint_ids)):
        justification = catalog.get(constraint_id)
        if justification is None:
            signals.append(
                {
                    "constraint_id": constraint_id,
                    "reason": "missing_justification",
                    "status": None,
                    "review_epoch": None,
                }
            )
            continue
        if justification.status == "legacy":
            signals.append(
                {
                    "constraint_id": constraint_id,
                    "reason": "legacy_status",
                    "status": justification.status,
                    "review_epoch": justification.review_epoch,
                }
            )
            continue
        if current_epoch - justification.review_epoch > review_window:
            signals.append(
                {
                    "constraint_id": constraint_id,
                    "reason": "stale_review",
                    "status": justification.status,
                    "review_epoch": justification.review_epoch,
                }
            )
    return signals


__all__ = [
    "ConstraintJustification",
    "DoctrineReference",
    "constraint_justification_catalog",
    "enumerate_constraint_review_signals",
    "get_constraint_justification",
]
