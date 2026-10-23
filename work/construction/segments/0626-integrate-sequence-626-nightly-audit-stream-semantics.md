# Sequence 626 — integrate configured nightly audit stream verification

Sequence 626 corrects the nightly audit workflows to invoke the strict verifier in configured-stream mode. The configured audit streams carry independent recorded anchors; passing `logs/` selected a single directory-wide chain and produced a false cross-stream mismatch. The fix retains hosted Administrator preflight, `sudo -n`, `--strict`, `--no-input`, read-only audit authority, and the existing separately gated repair path.

PR #2707 candidate `866549d7f2eb04e26374781880f35af945b9f705` (tree `dd76eea85e4d6298fdd3d63d7dfbf887b56caae1`) merged normally into main as `932ddb7405015723b89d4a117cdcb80cc2327bf0` (tree `dd76eea85e4d6298fdd3d63d7dfbf887b56caae1`). The merge retained source candidate history, with the prior main `f4faf307544f7c697a6a1cab23577521e3d8b467` as first parent and the tested candidate as second parent.

## Exact-candidate verification

Required Quality Gate #39980564757 passed strict hosted Administrator audits, exact acceptance binding, hosted landing finalization, and the separate pre-publication metadata guard. Candidate CI #39980564501 passed source validation, self-check/pytest, strict documentation linkcheck, and Helm/Kubernetes. Invariants #39980564483, Docker #39980564540, Codex CI #39980564714, lint #39980564524, release #39980564692, and gradient regression #39980564700 passed.

## Post-merge main verification

On exact source main `932ddb7405015723b89d4a117cdcb80cc2327bf0`, Required Quality Gate #39981734541, CI #39981734360, Docker #39981734353, Docs Deploy #39981734612, Codex CI #39981734423, Invariant Tests #39981734322, Nightly Self Check #39981734391, and Nightly Audit Integrity #39981734328 passed. CI completed source validation and the integrated resource-to-cognition lifecycle, pytest/Mypy self-check, strict Sphinx linkcheck, and Helm/Kubernetes. Forge Smoke #39981734307 was skipped by workflow conditions.

The push-triggered Nightly Audit Integrity execution ran on this exact main commit. Hosted Administrator availability and strict audit verification passed: all four configured logs were valid (100.0%), the independent audit-chain report was `ok`, the strict bucket was `healthy_strict`, and the repair job was skipped because no repair was required.

## Append-only evidence correction

Independent GitHub readback of PR #2705's changed-file list shows that the sequence-625 evidence JSON recorded an inaccurate `source.changed_paths` list. The actual changed paths were `sentientos/federation/semantic_review_docket.py`, `sentientos/private_file_custody.py`, `tests/integrity/test_repo_invariant_tripwire.py`, and `tests/test_federation_peer_authentication.py`. The two test paths recorded in the earlier JSON do not match that PR's changed-file list or candidate tree. The source code and tests themselves are present in the verified candidate; this is a record-path attribution error. Sequence 626 appends this correction and leaves the original segment and evidence bytes unchanged.

The main active checkpoint also still began with sequence 624 although its custody index bound the checkpoint to sequence 625. This checkpoint update advances the current-state summary while retaining its historical sequence sections. No prior segment or evidence is rewritten.

This segment follows `segment-sha256:7c39f1dea5d38c917f447092a30c85f2e6431c847428dccf822ad824042c6ecd`.
