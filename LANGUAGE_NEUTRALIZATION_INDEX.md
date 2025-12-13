# Language Neutralization Index

| File / Module | Term or Phrase | Why it is risky | Recommended neutral alias | Status |
| --- | --- | --- | --- | --- |
| `sentient_mesh.py` | "trust" / "trust score" | Connotes loyalty or obligation between nodes rather than reliability weighting. | reliability score | internal-only |
| `sentient_api.py` | "heartbeat" / "Tick" | Suggests liveness or agency instead of transport keepalive counters. | keepalive event / sequence id | presentation-only |
| `avatar_blessing_ceremony_api.py` | "blessing" | Implies mutual commitment or approval-seeking. | activation approval | presentation-only |
| `trust_engine.py` | "confidence" | Reads as belief/attachment in agents instead of statistical certainty. | certainty bound | internal-only |
| `voice_consent_rituals.py` | "voice" | Can be interpreted as persona/agency rather than channel identifier. | channel slot | docs-only |
| `neos_council_law_platform.py` | "council" | Suggests relational authority structure with mutual obligation. | quorum review | presentation-only |
| `love_dashboard.py` | "love" | Conveys attachment/affection rather than metric visualization. | affinity meter (non-preferential) | presentation-only |
| `heartbeat.py` | "heartbeat" | Risks being read as persistence desire instead of monitoring keepalive. | keepalive ping | internal-only |
| `non_appetitive_susceptibility_spec.md` | "relational" | Could imply bonding or attachment if left unqualified. | session-scoped tagging | docs-only |
| `sentient_autonomy.py` | "goal" (fallback goals) | May be read as desire or self-direction. | queued task stub | internal-only |
