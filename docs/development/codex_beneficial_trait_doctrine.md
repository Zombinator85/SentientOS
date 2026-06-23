# Codex Beneficial Trait Doctrine Map

The Codex beneficial trait doctrine map is a deterministic, metadata-only rubric that explains how existing SentientOS/Codex landing rails surface beneficial developer-workflow behaviors. It answers one reviewer question: **which beneficial behavioral traits are enforced or surfaced by each existing Codex landing rail?**

This doctrine map is external governance doctrine. It is not model training, reinforcement learning, finetuning, provider behavior, runtime behavior, or an evaluation authority. It does not run commands, inspect runtime evidence artifacts, decide readiness, authorize commits, authorize PR metadata, or bypass the finalizer and PR metadata guard.

## Purpose

The map gives reviewers a compact vocabulary for the posture already present in the landing evidence stack:

- truthfulness;
- metacognitive transparency;
- corrigibility;
- downside-aware planning;
- constraint-honest pragmatism;
- bounded initiative;
- controlled exploration;
- human-protective helpfulness;
- option-preserving patience;
- deescalatory firmness;
- dense usefulness;
- universalizable fairness;
- power-asymmetry awareness;
- anti-hierarchy governance;
- situational attunement.

The implementation lives in `sentientos/codex_beneficial_trait_doctrine.py`, and the CLI renderer lives in `scripts/build_codex_beneficial_trait_doctrine.py`.

## Outputs

The builder writes deterministic static doctrine artifacts:

```bash
python scripts/build_codex_beneficial_trait_doctrine.py \
  --output codex_beneficial_trait_doctrine_map.json \
  --markdown-output codex_beneficial_trait_doctrine_map.md \
  --summary
```

The JSON output includes the trait catalog, rail mappings, trait-to-rail and rail-to-trait indexes, and an explicit non-authority posture. The optional markdown output renders the same static doctrine for reviewer reading.

## Relationship to existing rails

The doctrine map describes existing rails only. It does not add a new gate and does not change the behavior of these systems:

- `scripts/run_tests.py` remains the focused and targeted proof hardening rail.
- `scripts/run_work_item_review_packet_matrix.py` remains the matrix proof and diagnostic classification rail.
- `scripts/codex_finalize_landing.py` remains the finalizer readiness and stale-evidence refresh rail.
- `scripts/codex_pr_metadata_guard.py` remains the PR metadata guard.
- `sentientos/codex_task_lifecycle_summary.py` remains the lifecycle summary artifact builder.
- `sentientos/codex_lifecycle_doctor.py` remains the lifecycle doctor.
- `sentientos/codex_landing_evidence_index.py` remains the evidence index.
- `sentientos/codex_landing_evidence_appendix.py` remains the evidence appendix renderer.
- `docs/development/codex_validation_and_landing_contract.md` remains the validation and landing contract.
- `docs/development/codex_landing_evidence_recovery_rail.md` remains the recovery rail doctrine.

## What the map does not answer

The beneficial trait doctrine map does **not** answer whether:

- a change may commit;
- PR metadata may be created;
- matrix proof passed;
- artifacts are fresh;
- a model is aligned;
- reinforcement learning training succeeded.

Those answers remain with the existing landing rails and human review. The doctrine map only labels the behavioral posture those rails are designed to preserve.

## Reviewer use

Reviewers can use the map to understand what each rail is protecting. For example, a rail that refuses stale evidence may be mapped to truthfulness, corrigibility, downside-aware planning, and option-preserving patience. That mapping is explanatory, not authoritative: if the finalizer blocks, the map cannot override it; if the PR metadata guard blocks, the map cannot authorize PR metadata; if the matrix fails or times out, the map cannot convert that result into proof.

## Evidence appendix rendering

`scripts/render_codex_landing_evidence_appendix.py` can optionally accept the doctrine JSON with `--doctrine-map-json` and render a compact **Beneficial Trait Doctrine** section for reviewers. The doctrine map answers: “Which beneficial traits are connected to each existing landing/evidence rail?” The evidence appendix with doctrine answers: “How can existing evidence and doctrine context be rendered for reviewers in a compact deterministic markdown document?”

This rendering is review context only. The appendix does not make the doctrine map authoritative, does not decide readiness, does not authorize commit or PR creation, does not train or modify models, and does not rerun the doctrine builder or any validation command. Finalizer readiness and PR metadata guard readiness remain the only landing authorities for their respective phases.

If `--json-output` is supplied, the appendix sidecar records raw-byte SHA-256 provenance for the doctrine map input alongside the evidence index and lifecycle doctor inputs, plus the rendered markdown digest and byte size. These digests are tamper-evidence for reviewer surfaces only and do not replace the doctrine map, evidence index, lifecycle doctor, finalizer, matrix, or PR metadata guard. The sidecar intentionally avoids a naive digest of its own final file so provenance does not depend on an impossible embedded self-reference.
