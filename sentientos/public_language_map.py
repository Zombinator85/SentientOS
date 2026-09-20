"""Context-aware terminology registry for public SentientOS surfaces."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final
@dataclass(frozen=True)
class PublicTerm:
    legacy_term: str
    normalized_term: str
    migration_status: str
    compatibility_alias: bool
    deprecation_note: str
    rationale: str
def _legacy(term: str, normalized: str, rationale: str, *, alias: bool = True) -> PublicTerm:
    return PublicTerm(term, normalized, "compatibility_alias" if alias else "retired_public_term", alias, "Use the descriptive term on new public surfaces.", rationale)
PUBLIC_LANGUAGE_MAP: Final[dict[str, PublicTerm]] = {
 "cathedral": _legacy("cathedral", "governance control plane", "Names operator and policy custody."),
 "blessing": _legacy("blessing", "approval or authorization", "Names the actual gate result."),
 "ritual": _legacy("ritual", "procedure or workflow", "Names a repeatable process."),
 "saint": _legacy("saint", "contributor, auditor, or reviewer", "Names the actual role.", alias=False),
 "liturgy": _legacy("liturgy", "policy or operating procedure", "Names reviewed doctrine.", alias=False),
 "covenant": _legacy("covenant", "integrity policy or invariant set", "Names deterministic constraints."),
 "sanctuary": _legacy("sanctuary", "protected execution boundary", "Names isolation.", alias=False),
 "consciousness layer": _legacy("consciousness layer", "cognition layer", "Mechanisms do not establish phenomenology."),
 "consciousness cycle": _legacy("consciousness cycle", "cognitive cycle", "Names cognitive integration."),
 "inner narrator": _legacy("inner narrator", "reflection summarizer", "Creates bounded summaries."),
 "sentience kernel": _legacy("sentience kernel", "goal-selection kernel", "Proposes bounded goals."),
 "forge": _legacy("forge", "governed change pipeline", "Names staged change."),
 "vow": _legacy("vow", "integrity policy store", "Internal path compatibility."),
 "glow": _legacy("glow", "state and evidence store", "Internal path compatibility."),
 "pulse": _legacy("pulse", "event bus or telemetry stream", "Internal path compatibility."),
}
CONTEXT_SENSITIVE_TERMS: Final[frozenset[str]] = frozenset({"council", "presence", "self-model", "trust", "oracle", "witness", "healing"})
def translate_public_term(term: str) -> PublicTerm | None: return PUBLIC_LANGUAGE_MAP.get(term.strip().lower())
__all__ = ["CONTEXT_SENSITIVE_TERMS", "PUBLIC_LANGUAGE_MAP", "PublicTerm", "translate_public_term"]
