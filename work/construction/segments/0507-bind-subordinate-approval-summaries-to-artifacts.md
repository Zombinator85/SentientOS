# Sequence 507 — bind subordinate approval summaries to artifacts

The live transition request contains both the subordinate approval artifacts and a compact identity/digest summary. Request authentication protects both fields from outside modification, but the runtime previously forwarded the artifacts without checking that the summary described those exact artifacts. This increment makes the transition owner derive the summary again at ingress and require exact ordered equality before calling the subordinate verifier or advancing the controller. Missing summaries and mismatches fail closed.

The summary derivation is shared by request construction and runtime validation. Negative regressions re-sign correctly authenticated requests whose summaries are missing or disagree with the attached artifact, proving the rejection happens before subordinate verification and controller effects. The CI source-validation acceptance step includes both exact regression nodes.

Sequence 506 was merged regularly as 564bff002c4bd0a679bfa8347c0478b1698e0a2d, tree 24360d2bbf2592e4810ff011f9fc6520569e156c, with ordered parents 1a568708d31201885034a51b66319b770584b5d4 and 79aa1d0cdf776754af1b746bd511c9af45142e87. Its post-merge Quality Gate, source validation, self-check, invariants, CPU smoke, docs, builds, Helm, and Pages deployment passed; Forge smoke was skipped by condition.

Supplemental local verification passed 97 tests across transition ingress, model transition progression, daemon composition, and the source-validation workflow contract. Targeted Mypy, compilation, workflow YAML parsing, diff checks, and construction custody passed. The local full Mypy baseline helper reports a toolchain mismatch because the sandbox exposes Mypy only through user-site packages under its sanitized environment; the hosted sequence 506 baseline passed, and sequence 507 hosted baseline verification remains pending.

No production transition, activation, serving, inference, or writeback was performed.

Verified main source: 564bff002c4bd0a679bfa8347c0478b1698e0a2d
Verified main tree: 24360d2bbf2592e4810ff011f9fc6520569e156c
Implementation source commit: a5b689b822f6349f34766ea93399278f12bf308b
Implementation source tree: e169c02e93895874cf7748769203a8acf559331e
Latest construction segment: work/construction/segments/0507-bind-subordinate-approval-summaries-to-artifacts.md
Sequence: 507 (candidate pending hosted verification)
