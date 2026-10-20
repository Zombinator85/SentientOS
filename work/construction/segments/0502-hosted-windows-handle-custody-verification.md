# Sequence 502 — hosted Windows handle-custody verification

PR #2504 adds a least-privilege Windows runtime workflow, a source-bound task-acceptance manifest, and regressions for the existing bounded Windows custody reader. Canonical work-plan evidence still fails closed on Windows because descriptor-relative writing is not implemented; this increment adds no Windows write path and grants no new mutation authority.

The first native Windows run exposed a fixture issue: the hosted runner's temporary directory owner did not match the production reader's current-user ownership requirement. The test now assigns its disposable directory and file to the current user with private ACLs. Production ACL validation was unchanged. On Windows Server 2025, all five regression nodes then passed. The clean Linux workspace ran the portable bounded-read node successfully and skipped the four native-only nodes; targeted Mypy, compilation, YAML parsing, source blob identities, and diff checks passed.

The exact PR candidate was 64f34d8dd81ca0dbbb6914258d387f4ec6ec1c65, tree a3b3e6d94b75529a8239d80106875f35ab816b99. It passed CI, Windows Custody, Required Quality Gate, Codex CI, invariants, Gradient null regression, Release, Docker, and Lint Benchmark. The Quality Gate's hosted Administrator strict audits and immutability check passed, as did exact-node acceptance and the separate pre-publication metadata guard. All three artifacts were independently downloaded and matched GitHub's SHA-256 digests. The finalizer bound the exact candidate, used the solo profile, and explicitly did not request the exhaustive matrix.

PR #2504 merged with history preserved as signed merge ff37f74eca914153cc7435ad528aa844258cabcf. Its ordered parents are verified main 675d7478a51c23b86c067e863b220d25b8ed29ef and candidate 64f34d8dd81ca0dbbb6914258d387f4ec6ec1c65. Remote main resolves to the merge, and the signed merge tree equals the candidate tree. Post-merge CI, Quality Gate, Codex CI, invariants, Docs Deploy, Docker, and Windows Custody passed. Forge Smoke skipped under its workflow condition.

The scheduled Federation Health run 39463524054 also executed on this exact main head. Its hosted Administrator preflight and report generation succeeded. The artifact digest matched GitHub's digest, and the report hash matched its bound receipt. The report records one configured local-log node, zero recent events, and a 2025-06-05 latest event; it explicitly says this is a local log snapshot, not live federation telemetry. The separate publish job failed because repository Actions settings prohibit GITHUB_TOKEN from creating pull requests. That failure is not counted as health-generation failure or successful publication.

The latest scheduled Nightly Audit Integrity and Nightly Self Check successes remain bound to older heads 124de0f9ced349de7342901a2e1338c460c05a00 and 5a3df4c811e07aa7a038c2ab48c4d25f521b1095. Both passed hosted Administrator preflight and strict audit verification; the audit repair job skipped. These are historical results, not current-head scheduled evidence. No production inference, campaign, or transition was performed.

Latest source merge: `ff37f74eca914153cc7435ad528aa844258cabcf`, tree `a3b3e6d94b75529a8239d80106875f35ab816b99`
Latest segment: work/construction/segments/0502-hosted-windows-handle-custody-verification.md
Predecessor segment SHA-256: 3483bf789523bb2429fb7597a16d3e56928ce5de53661a0a08ce4758c1d4f390
Sequence: 502
