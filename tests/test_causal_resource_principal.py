from __future__ import annotations
from dataclasses import FrozenInstanceError, fields, replace
import hashlib, inspect
import pytest
import sentientos.causal_resource_principal as module
from sentientos.causal_resource_principal import *
pytestmark=pytest.mark.no_legacy_skip
SP="sha256:"+"1"*64; SU="sha256:"+"2"*64; I="2026-09-21T08:00:00Z"; E="2026-09-21T09:00:00Z"; N="2026-09-21T08:30:00Z"
class Sponsor:
 def __init__(self,digest: str=SP,reject: bool=False): self.digest=digest; self.reject=reject; self.seen: list[object]=[]
 def verify(self,evidence: object)->VerifiedOperatorSponsorship:
  self.seen.append(evidence)
  if self.reject: raise ValueError
  return VerifiedOperatorSponsorship(self.digest)
def mint(verifier: object|None=None, issuer: str="resource-principal-issuer", **kw: object)->CausalResourcePrincipal:
 v={"sponsorship_evidence":{"signed":"operator"},"subject_binding_digest":SU,"epoch":1,"issued_at":I,"expires_at":E}; v.update(kw)
 return RootPrincipalIssuer(issuer_id=issuer,sponsorship_verifier=verifier or Sponsor()).mint_root(**v) # type: ignore[arg-type]
def verify(p: CausalResourcePrincipal,**kw: object)->CausalResourcePrincipal:
 return CausalResourcePrincipalVerifier().verify(p,current_time=N,**kw) # type: ignore[arg-type]
def test_valid_explicitly_sponsored_root_is_inert_and_verifiable() -> None:
 s=Sponsor(); p=mint(s); assert s.seen and verify(p)==p; assert p.root_principal_id==p.principal_id and p.parent_principal_id is None and p.previous_generation_digest==GENESIS_PREDECESSOR_DIGEST
def test_sponsorship_verification_is_required_and_fails_closed() -> None:
 with pytest.raises(CausalResourcePrincipalError): RootPrincipalIssuer(issuer_id="issuer",sponsorship_verifier=None) # type: ignore[arg-type]
 with pytest.raises(CausalResourcePrincipalError): mint(Sponsor(reject=True))
 class Bad:
  def verify(self,evidence: object)->object: return {"evidence_digest":SP}
 with pytest.raises(CausalResourcePrincipalError): mint(Bad())
def test_caller_cannot_supply_principal_id_and_no_allow_all_exists() -> None:
 assert "principal_id" not in inspect.signature(RootPrincipalIssuer.mint_root).parameters
 with pytest.raises(TypeError): mint(principal_id="root")
 assert not any("allow" in n.lower() and "sponsor" in n.lower() for n in vars(module))
def test_deterministic_inputs_and_each_identity_input_changes_id() -> None:
 p=mint(); variants=[mint(Sponsor("sha256:"+"3"*64)),mint(subject_binding_digest="sha256:"+"4"*64),mint(epoch=2),mint(issued_at="2026-09-21T08:01:00Z"),mint(expires_at="2026-09-21T10:00:00Z"),mint(issuer="other-issuer")]
 assert mint()==p and all(x.principal_id!=p.principal_id and x.binding_digest!=p.binding_digest for x in variants)
def test_fixed_canonical_vector_and_independent_binding_recomputation() -> None:
 p=mint(); assert p.principal_id=="crp-sha256:906b35862977e1ee004c33046e4e76f23c7be9beffc86af464ee28eb0e3fd8dd"; assert p.binding_digest=="sha256:5d3496cb6e888442d98c928cc64b2bfbb133ecd2ff7dd3878a94ac0b2a2987e7"
 body=p.to_dict(); claimed=body.pop("binding_digest"); assert claimed=="sha256:"+hashlib.sha256(canonical_bytes(body)).hexdigest()
@pytest.mark.parametrize("field,value",[("schema","bad"),("principal_id","crp-sha256:"+"f"*64),("root_principal_id","x"),("parent_principal_id","x"),("sponsor_evidence_digest","sha256:"+"3"*64),("subject_binding_digest","sha256:"+"4"*64),("epoch",2),("issued_at","2026-09-21T08:01:00Z"),("expires_at","2026-09-21T10:00:00Z"),("issuer_id","other"),("previous_generation_digest","sha256:"+"5"*64),("binding_digest","sha256:"+"6"*64)])
def test_tampering_every_semantic_field_fails(field: str,value: object) -> None:
 with pytest.raises(CausalResourcePrincipalError): verify(replace(mint(),**{field:value})) # type: ignore[arg-type]
@pytest.mark.parametrize("extra",[{"unknown":1},{"capability":"external_model_inference"},{"grant":"approved"},{"admission":"approved"},{"quota":"unlimited"},{"resource_limits":{"gpu":"all"}}])
def test_mapping_rejects_unknown_authority_and_allocation_smuggling(extra: dict[str,object]) -> None:
 with pytest.raises(CausalResourcePrincipalError): CausalResourcePrincipal.from_mapping(mint().to_dict()|extra)
@pytest.mark.parametrize("kw",[{"subject_binding_digest":"trusted"},{"epoch":0},{"epoch":-1},{"issued_at":"bad"},{"expires_at":I},{"expires_at":"2026-09-21T07:00:00Z"}])
def test_mint_rejects_malformed_inputs(kw: dict[str,object]) -> None:
 with pytest.raises(CausalResourcePrincipalError): mint(**kw)  # type: ignore[arg-type]
def test_expiry_not_yet_valid_and_expectation_mismatches_fail() -> None:
 p=mint(); v=CausalResourcePrincipalVerifier()
 for kw in ({"current_time":"2026-09-21T07:59:59Z"},{"current_time":E},{"current_time":N,"expected_issuer_id":"other"},{"current_time":N,"expected_sponsor_evidence_digest":"sha256:"+"3"*64},{"current_time":N,"expected_subject_binding_digest":"sha256:"+"4"*64},{"current_time":N,"expected_epoch":2}):
  with pytest.raises(CausalResourcePrincipalError): v.verify(p,**kw)
def test_immutable_exact_round_trip_and_thin_surface() -> None:
 p=mint()
 with pytest.raises(FrozenInstanceError): p.epoch=2 # type: ignore[misc]
 assert verify(CausalResourcePrincipal.from_mapping(p.to_dict()))==p
 names={f.name for f in fields(CausalResourcePrincipal)}; assert names==set(module._FIELDS)
 forbidden={"cpu","ram","memory_limit","gpu","vram","tokens","token_limit","api_calls","provider_spend","retries","proof_budget","quota","amount","resource_limits","scheduling_priority","deadline_budget","capability","grant","admission","required_effect","authorized_effect","runtime_authority","work_item_id"}; assert names.isdisjoint(forbidden)
 assert not hasattr(RootPrincipalIssuer,"mint_child") and not any(n in vars(module) for n in {"ResourceAllocation","ResourceConsumptionReceipt","ResourceDelegation","ResourceReservation","ChildPrincipalIssuer","ResourceScheduler"})
def test_wildcard_broad_issuer_and_malformed_sponsor_fail() -> None:
 for issuer in ("","*","operator*","all","any"):
  with pytest.raises(CausalResourcePrincipalError): RootPrincipalIssuer(issuer_id=issuer,sponsorship_verifier=Sponsor())
 with pytest.raises(CausalResourcePrincipalError): mint(Sponsor("trusted"))
