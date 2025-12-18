from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping, Sequence


OUTDATED_SYMBOLS = {"legacy", "deprecated", "obsolete"}


def _flatten_text(blobs: Iterable[str]) -> list[str]:
    phrases: list[str] = []
    for blob in blobs:
        for chunk in str(blob).split(","):
            cleaned = chunk.strip()
            if cleaned:
                phrases.append(cleaned)
    return phrases


def _canon_mismatch(identity_fragments: Mapping[str, object]) -> float:
    canon = set(_flatten_text(identity_fragments.get("canon", [])))
    current = set(_flatten_text(identity_fragments.get("current", [])))
    if not canon:
        return 0.0
    agreement = len(canon & current) / len(canon)
    return round(1 - agreement, 2)


def _symbolic_drift(glow_digests: Sequence[Mapping[str, object]] | Sequence[str]) -> float:
    tokens: list[str] = []
    for digest in glow_digests:
        if isinstance(digest, Mapping):
            tokens.extend(_flatten_text(digest.values()))
        else:
            tokens.extend(_flatten_text([digest]))
    counter = Counter(token.lower() for token in tokens)
    outdated_hits = 0
    for token, count in counter.items():
        token_lower = token.lower()
        if token_lower in OUTDATED_SYMBOLS or any(symbol in token_lower for symbol in OUTDATED_SYMBOLS):
            outdated_hits += count
    if not tokens:
        return 0.0
    return min(1.0, outdated_hits / max(len(tokens), 1))


def _feedback_divergence(mood_logs: Sequence[Mapping[str, object]]) -> float:
    divergences: list[float] = []
    for entry in mood_logs:
        expected = entry.get("expected") or entry.get("expected_feedback")
        received = entry.get("received") or entry.get("actual_feedback")
        if expected is None or received is None:
            continue
        divergences.append(1.0 if str(expected).strip().lower() != str(received).strip().lower() else 0.0)
    if not divergences:
        return 0.0
    return round(sum(divergences) / len(divergences), 2)


def audit_persona_decay(
    persona: str,
    glow_digests: Sequence[Mapping[str, object]] | Sequence[str],
    mood_logs: Sequence[Mapping[str, object]],
    identity_fragments: Mapping[str, object],
) -> dict:
    """Analyze logs to surface identity drift risks."""

    canon_score = _canon_mismatch(identity_fragments)
    symbolic_score = _symbolic_drift(glow_digests)
    feedback_score = _feedback_divergence(mood_logs)

    weights = (0.4, 0.3, 0.3)
    drift_score = round(
        min(1.0, (canon_score * weights[0]) + (symbolic_score * weights[1]) + (feedback_score * weights[2])),
        2,
    )

    symptom_candidates = {
        "canon mismatch": canon_score,
        "symbolic drift": symbolic_score,
        "feedback divergence": feedback_score,
    }
    dominant_symptom = max(symptom_candidates, key=symptom_candidates.get)

    symptom_labels = {
        "canon mismatch": "canon mismatch drift",
        "symbolic drift": "symbolic drift",
        "feedback divergence": "feedback divergence drift",
    }
    symptom = symptom_labels.get(dominant_symptom, dominant_symptom)

    action = "suggest identity reaffirmation prompt"
    if dominant_symptom == "feedback divergence":
        action = "re-engage with user alignment check-in"

    return {
        "persona": persona,
        "drift_score": drift_score,
        "symptom": symptom,
        "action": action,
    }


__all__ = ["audit_persona_decay"]
