# Sequence 657: Component-aware Cathedral path safety

The roadmap lists path ancestry as an independent security follow-up. Review of `AmendmentApplicator._is_safe_value` found that raw `startswith` checks could admit a sibling whose name begins with the configured root and traversal text that begins with that root. The bounded fix canonicalizes path-like strings and requires component-aware ancestry with `Path.relative_to`; invalid or unresolved paths fail closed. It retains amendment-domain admission and existing persistence/effect boundaries.

Regression coverage proves a normal in-root descendant is accepted, sibling-prefix and root-prefixed traversal values are rejected, and a rejected amendment produces neither configuration persistence nor a ledger entry. The new cases are explicitly exempted from the legacy test quarantine and `tests/test_cathedral_apply.py` is now part of the canonical test paths.

Validation on base source SHA `93706511d5e0389f4a4820c771e84b5b3a47587f`: canonical suite run `c520a88294d6492ab8d018edf3cf1e6c` selected 166, passed 150, skipped 16, failed 0; provenance SHA-256 `e539a4568d208f60d09d954981cdc1af12f1c91545e31521d1892392b1ce15af`. Exact-node acceptance is `task_acceptance_ready`. Targeted mypy and `git diff --check` passed. The docs dependency check and build passed with 616 generated pages. Custody verified all 656 prior segments.

This remains an uncommitted construction candidate; no PR publication or hosted result is implied by this record. Source-file SHA-256 values are recorded in the evidence JSON.

Evidence: `work/construction/evidence/0657-component-aware-cathedral-path-safety.json` (SHA-256 `10a2728a2a89b153a711872239ec64a04ae6605a2aade6ead9dcc879fb48071e`).
