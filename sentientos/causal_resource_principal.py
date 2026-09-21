"""Inert deterministic evidence for one operator-sponsored root causal activity.

A principal grants nothing, allocates nothing, and performs no effects. Children,
allocations, propagation, revocation custody, and renewal are deliberately absent.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib, json, re
from typing import Any, Mapping, Protocol

SCHEMA = "sentientos.causal_resource_principal:v1"
GENESIS_PREDECESSOR_DIGEST = "sha256:" + "0" * 64
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_PRINCIPAL = re.compile(r"crp-sha256:[0-9a-f]{64}")
_ISSUER = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}")
_FIELDS = frozenset(("schema","principal_id","root_principal_id","parent_principal_id","sponsor_evidence_digest","subject_binding_digest","epoch","issued_at","expires_at","issuer_id","previous_generation_digest","binding_digest"))

class CausalResourcePrincipalError(ValueError): pass

@dataclass(frozen=True)
class VerifiedOperatorSponsorship:
    """Authenticated provenance result, not a grant or resource record."""
    evidence_digest: str

class OperatorSponsorshipVerifier(Protocol):
    """Injected authentication boundary; no allow-all implementation is supplied."""
    def verify(self, sponsorship_evidence: object) -> VerifiedOperatorSponsorship: ...

def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()

def _seal(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()

def _valid_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None or value == GENESIS_PREDECESSOR_DIGEST:
        raise CausalResourcePrincipalError(f"invalid_{label}")
    return value

def _valid_issuer(value: object) -> str:
    if not isinstance(value, str) or _ISSUER.fullmatch(value) is None or "*" in value or value in {"all", "any"}:
        raise CausalResourcePrincipalError("invalid_issuer_id")
    return value

def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CausalResourcePrincipalError(f"invalid_{label}")
    try: parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc: raise CausalResourcePrincipalError(f"invalid_{label}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != value:
        raise CausalResourcePrincipalError(f"noncanonical_{label}")
    return parsed

def _identity(sponsor: str, subject: str, epoch: int, issued: str, expires: str, issuer: str) -> dict[str, object]:
    return {"schema":SCHEMA,"sponsor_evidence_digest":sponsor,"subject_binding_digest":subject,"epoch":epoch,"issued_at":issued,"expires_at":expires,"issuer_id":issuer,"previous_generation_digest":GENESIS_PREDECESSOR_DIGEST}

def _id(identity: Mapping[str, object]) -> str: return "crp-" + _seal(dict(identity))

@dataclass(frozen=True)
class CausalResourcePrincipal:
    schema: str; principal_id: str; root_principal_id: str; parent_principal_id: None
    sponsor_evidence_digest: str; subject_binding_digest: str; epoch: int
    issued_at: str; expires_at: str; issuer_id: str; previous_generation_digest: str; binding_digest: str
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> CausalResourcePrincipal:
        if set(value) != _FIELDS: raise CausalResourcePrincipalError("principal_fields_not_exact")
        try: candidate = cls(**dict(value))  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc: raise CausalResourcePrincipalError("malformed_principal") from exc
        return CausalResourcePrincipalVerifier().verify(candidate, current_time=candidate.issued_at)

class CausalResourcePrincipalVerifier:
    def verify(self, evidence: CausalResourcePrincipal | Mapping[str, object], *, current_time: str,
               expected_issuer_id: str | None=None, expected_sponsor_evidence_digest: str | None=None,
               expected_subject_binding_digest: str | None=None, expected_epoch: int | None=None) -> CausalResourcePrincipal:
        p = evidence if isinstance(evidence, CausalResourcePrincipal) else CausalResourcePrincipal.from_mapping(evidence)
        if p.schema != SCHEMA: raise CausalResourcePrincipalError("unsupported_schema")
        if _PRINCIPAL.fullmatch(p.principal_id) is None: raise CausalResourcePrincipalError("invalid_principal_id")
        if p.root_principal_id != p.principal_id: raise CausalResourcePrincipalError("invalid_root_relationship")
        if p.parent_principal_id is not None: raise CausalResourcePrincipalError("root_parent_forbidden")
        if p.previous_generation_digest != GENESIS_PREDECESSOR_DIGEST: raise CausalResourcePrincipalError("invalid_genesis_predecessor")
        _valid_issuer(p.issuer_id); _valid_digest(p.sponsor_evidence_digest,"sponsor_evidence_digest"); _valid_digest(p.subject_binding_digest,"subject_binding_digest")
        if type(p.epoch) is not int or p.epoch < 1: raise CausalResourcePrincipalError("invalid_epoch")
        issued, expires, now = _time(p.issued_at,"issued_at"), _time(p.expires_at,"expires_at"), _time(current_time,"current_time")
        if expires <= issued: raise CausalResourcePrincipalError("invalid_validity_window")
        if now < issued: raise CausalResourcePrincipalError("principal_not_yet_valid")
        if now >= expires: raise CausalResourcePrincipalError("principal_expired")
        identity = _identity(p.sponsor_evidence_digest,p.subject_binding_digest,p.epoch,p.issued_at,p.expires_at,p.issuer_id)
        if p.principal_id != _id(identity): raise CausalResourcePrincipalError("principal_id_mismatch")
        body=p.to_dict(); claimed=body.pop("binding_digest")
        if not isinstance(claimed,str) or _DIGEST.fullmatch(claimed) is None or claimed != _seal(body): raise CausalResourcePrincipalError("binding_digest_mismatch")
        for expected,actual,error in ((expected_issuer_id,p.issuer_id,"issuer_mismatch"),(expected_sponsor_evidence_digest,p.sponsor_evidence_digest,"sponsor_mismatch"),(expected_subject_binding_digest,p.subject_binding_digest,"subject_mismatch"),(expected_epoch,p.epoch,"epoch_mismatch")):
            if expected is not None and expected != actual: raise CausalResourcePrincipalError(error)
        return p

class RootPrincipalIssuer:
    def __init__(self, *, issuer_id: str, sponsorship_verifier: OperatorSponsorshipVerifier) -> None:
        self._issuer_id=_valid_issuer(issuer_id)
        if sponsorship_verifier is None: raise CausalResourcePrincipalError("sponsorship_verifier_required")
        self._verifier=sponsorship_verifier
    def mint_root(self, *, sponsorship_evidence: object, subject_binding_digest: str, epoch: int, issued_at: str, expires_at: str) -> CausalResourcePrincipal:
        try: verified=self._verifier.verify(sponsorship_evidence)
        except Exception as exc: raise CausalResourcePrincipalError("operator_sponsorship_not_verified") from exc
        if not isinstance(verified,VerifiedOperatorSponsorship): raise CausalResourcePrincipalError("operator_sponsorship_not_verified")
        sponsor=_valid_digest(verified.evidence_digest,"sponsor_evidence_digest"); subject=_valid_digest(subject_binding_digest,"subject_binding_digest")
        if type(epoch) is not int or epoch < 1: raise CausalResourcePrincipalError("invalid_epoch")
        if _time(expires_at,"expires_at") <= _time(issued_at,"issued_at"): raise CausalResourcePrincipalError("invalid_validity_window")
        identity=_identity(sponsor,subject,epoch,issued_at,expires_at,self._issuer_id); pid=_id(identity)
        body: dict[str,object]={"schema":SCHEMA,"principal_id":pid,"root_principal_id":pid,"parent_principal_id":None,**identity}
        return CausalResourcePrincipal(**body,binding_digest=_seal(body))  # type: ignore[arg-type]
