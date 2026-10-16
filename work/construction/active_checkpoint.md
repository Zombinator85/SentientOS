# Active construction checkpoint

Sequence 276 fixes sequence 275's hosted acceptance artifact ordering. The hosted root gate (UID 0) and planning acceptance passed; the lifecycle suite itself completed, but its exact acceptance verifier read a later suite's provenance file and blocked. The workflow now verifies each suite's own provenance before another test invocation can replace it, and a regression pins this order. The workflow and task acceptance tests passed 22/22 locally. Sequence 276's complete hosted verification is pending.

Latest verified source commit: `3c9c5e1eccf36511b85cda038f29fab5e562d018`
Latest verified source tree: `10543720b7aca3205ee94516f6b848e2297e2969`
Latest segment: work/construction/segments/0276-acceptance-provenance-ordering.md
Latest segment SHA-256: `1ac2840dc2c60c56776a4e5477adbf7d10a3246b91325bca55d80ee0a1c38145`
Evidence: work/construction/evidence/0276-acceptance-provenance-ordering.json
Queue: work/construction/reconciliation_xix_queue.json
Sequence: 276

Next: wait for the full sequence 276 hosted run, including both exact acceptance gates and root audits; then continue F1-F8. External subject sessions and physical outcomes remain unverified.
