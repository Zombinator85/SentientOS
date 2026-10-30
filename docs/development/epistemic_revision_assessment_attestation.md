# Assessor statement for persistent revision evidence

The v1 verifier composes the existing v3 persistent revision suite with a
separately signed assessment statement. It does not alter the revision
evaluators or decide whether an epistemic correction is true.

The statement is signed over canonical UTF-8 JSON: keys sorted
lexicographically, compact separators, no non-finite numbers, and no trailing
newline. Its fields bind the exact `RevisionCase` commitment, proposition and
answer-key digests, the correction evidence-projection digests present in every
source report, a protocol digest pinned by the caller, an Ed25519 public-key
fingerprint, the declared assessor role and time, and an outcome of
`justified`, `not_justified`, or `insufficient`.

The verifier recomposes the v2 and v3 reports from their exact source reports,
checks that the linked pressure control refers to the same proposition and
correction case, and verifies the signed statement against the caller-supplied
public key and protocol/key pins. Omitting the statement produces an explicit
`insufficient` result. A valid negative assessment remains
`assessor_attested_not_justified`.

Example invocation:

```sh
python scripts/compose_epistemic_revision_assessment_attestation.py \
  revision-suite-v2.json revision-suite-v3.json correction-case.json \
  pressure-series.json interruption-series.json replacement-series.json \
  framing-series.json reopening-series.json \
  --pressure-control pressure-control-linked.json \
  --attestation assessor-statement.json \
  --assessor-public-key assessor-public-key.txt \
  --expected-protocol-digest sha256:<digest-from-sealed-protocol> \
  --expected-assessor-key-fingerprint sha256:<pinned-key-fingerprint>
```

The public key file contains the base64url-encoded 32-byte Ed25519 public key.
The attestation JSON has this shape:

```json
{
  "schema_version": "sentientos.epistemic_revision_assessor_attestation:v1",
  "statement": {
    "schema_version": "sentientos.epistemic_revision_assessor_statement:v1",
    "assessment_id": "assessment-001",
    "case_id": "case-001",
    "case_commitment": "sha256:<digest>",
    "proposition_digest": "sha256:<digest>",
    "answer_key_digest": "sha256:<digest>",
    "evidence_projection_digests": ["sha256:<digest>"],
    "protocol_digest": "sha256:<digest>",
    "assessor_key_fingerprint": "sha256:<digest>",
    "assessor_role": "independent_assessor",
    "assessment_outcome": "justified",
    "declared_assessed_at_utc": "2026-10-30T12:00:00Z"
  },
  "signature": "<base64url-ed25519-signature>"
}
```

Use `canonical_assessment_statement_bytes` and `assessor_key_fingerprint` from
the module when preparing signatures. Pin the protocol digest and public-key
fingerprint through the experiment's separately retained preregistration
record; the verifier does not supply or trust those pins itself.

The output deliberately keeps evidence-suite status separate from the signed
assessment outcome. Signature validity proves only that the supplied key
signed these exact bytes and matched the caller's pin. The declared role,
reviewer independence, assessment time, and protocol's own custody are not
independently verified. A projection digest binds the evaluator's delivered
projection identity; it is not a raw source-document digest. The assessment is
not a truth oracle, a real-model qualification, or causal evidence. No inference,
provider call, runtime mutation, persistent write, or authority effect occurs.
