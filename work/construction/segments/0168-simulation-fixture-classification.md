## 2026-10-13 checkpoint — mark deterministic invocation fixtures as simulation

- Continued from remotely verified source commit `7ad4ad33e1493519b73d16f44db807cbeaaeb3d0` / tree `c14ac5d597560e75743c6d0bb7012eff85e5ab1d`.
- The new installation-backed transfer fixture was emitting canonical receipts with `admitted_completed` and `local_model_inference=true`. The normal objective summary therefore reported `actual_nonsynthetic_inference_verified=true`, even though the issuer was a deterministic fake. This was a test-evidence misclassification.
- The dedicated fixture issuer now publishes `admitted_simulation` receipts with the local-inference effect false. It retains the actual installation-scoped storage and `ResidentCognitiveInvocationReceiptReader`, allowing the test to continue exercising real custody and canonical receipt validation without asserting real backend execution.
- The fresh-process test confirms history transfer remains 3/3 present, 0/3 withheld, 3/3 restored, while the execution classification stays non-synthetic=false. It does not change production behavior or claim learning.

Checks:
- Fresh-process source-bound task-family episode: passed.
- Compilation and UTF-8/NUL/whitespace checks passed.

Source commit: cc833d07bc76aac58d627b5eb9bd0c06911e0f3c
Source tree: 7dff568f399faafe07afc95c93b153eeeda80696
Changed test blob: 73028e4c9c6238fbcbdfb20cb35fa92f52ccde07
Construction remains unverified for production.

Next: trace the complete trust contract for `actual_nonsynthetic_inference_verified` from invocation issuer through serving admission and persisted receipt verification. Identify whether existing production mechanisms independently attest backend entry, or only verify owner-issued receipt claims. Do not manufacture that attestation.
