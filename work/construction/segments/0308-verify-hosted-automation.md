# Sequence 308 — Verify hosted automation and narrow repair authority

Sequence 307 left hosted Federation Health, strict audit, and nightly self-check execution as its next dependency. This checkpoint records the evidence now obtained and separates confirmed results from runs the GitHub connector cannot expose.

The Federation Health job run `39010139696` ran on a hosted Administrator: `sudo -n id -u` passed, and the generator completed under sudo with `{"nodes": 1, "recent": 0, "status": "quiet"}`. Its automatic PR step failed because repository policy disallows GitHub Actions from creating or approving pull requests with `GITHUB_TOKEN`. The generated file was reviewed through PR #2292, which changed only `docs/FEDERATION_HEALTH.md`, and merged as `7d80e976fdfe2c2b37fbc2598c294983ad1b2228`. Main readback matches the generated output.

The hosted Nightly Audit run `39011220239` succeeded. Its strict verifier ran through noninteractive sudo and reported `audit_chain_status: ok`, `strict_bucket: healthy_strict`, and acceptable readiness. No repair was needed in that run.

The first fully provisioned Nightly Self Check exposed test isolation defects: tests tried to write runtime governance state under production default `/glow/governor` as the unprivileged runner. PR #2297 added a session-scoped temporary governor root, a non-quarantined regression test, and exact path filters so changes to that test harness retrigger Self Check. Its hosted full pytest passed with 143 passed and 13 skipped; CI, source validation, Helm, docs, and the protected quality gate passed. PR #2297 merged regularly as `50d062baab7f838b1dfeaf9b79ec42c5da0e0a14`.

PR #2298 moved audit repair, evidence staging, push, and PR creation into a dependent job that runs only after strict audit failure. The normal audit job and workflow token remain read-only; only the conditional repair job receives `contents: write` and `pull-requests: write`. Hosted CI and the protected quality gate passed. The strict verifier attested source tree `1ad128e83fda57fe1288b59004f1a044040c959d`; compare confirms the merged main tree has no file differences from that verified candidate. PR #2298 merged regularly as `69ac1afcab987c92de252f94793fafb2b66474be`.

Post-merge workflow-run status for the new Self Check and split audit push runs is not visible through the available connector: its commit-workflow-run endpoint returns PR-triggered runs only, and the commit status endpoint exposes no Actions check runs. The exact main push path filters are present, but no push-run success is claimed here. The PR CI runs validate the identical source tree.

Two limitations remain explicit. First, both automation PR publishers are subject to the repository Actions setting that blocks `GITHUB_TOKEN` PR creation; enabling the repository setting or providing a narrowly scoped token is an external prerequisite. Second, the sequence-286 deleted-payload limitation remains unchanged: nine known payloads and one unidentified payload remain unrecoverable.

Next dependency: obtain access to the new main push-run results, resolve the repository PR-creation setting or provide an approved scoped token, then resume the next source-development dependency from this verified main state.

Verified main commit: `69ac1afcab987c92de252f94793fafb2b66474be`
Verified main tree: `1ad128e83fda57fe1288b59004f1a044040c959d`
Previous segment SHA-256: `742a0a185928a2a24a4691742090d385e46c19791f69fc1811cf0419453a04f5`
