# Active construction checkpoint

Sequence 308 records PR #2298's verified integration on `main` at `69ac1afcab987c92de252f94793fafb2b66474be`, tree `1ad128e83fda57fe1288b59004f1a044040c959d`. The regular merge preserves history; comparison with the verified PR head is ahead 1, behind 0, with no changed files.

The Federation Health hosted job `39010139696` ran its Administrator preflight and generator successfully. The generator reported one node, zero recent events, and quiet status. The automatic publisher was denied by the repository Actions setting that blocks PR creation via `GITHUB_TOKEN`; PR #2292 was opened through the connected GitHub integration and merged with only `docs/FEDERATION_HEALTH.md` changed. Main readback matches the generated content.

Nightly Audit run `39011220239` passed strict audit verification under noninteractive sudo with a healthy strict bucket and acceptable readiness. PR #2297 fixed the Self Check test root that previously wrote to `/glow/governor`: full hosted pytest passed with 143 passed, 13 skipped. PR #2298 then scoped audit repair write permissions to a conditional job; routine verification has read-only token authority and retains the Administrator gate.

PR #2297 and #2298 passed their hosted quality gates and full CI on source trees identical to their merged main trees. The protected QG finalizer ran as UID 0. The current GitHub connector exposes PR-triggered workflow runs but not main push-run listings; no post-merge Self Check or split-audit status is claimed from that missing view.

The repository Actions setting that permits GITHUB_TOKEN to create PRs, or a narrowly scoped repository token with Contents and Pull requests write access, remains necessary for unattended Health and repair PR publication. The sequence-286 deleted-payload limitation remains unchanged: nine known payloads and one unidentified payload are unrecoverable.

Next dependency: make the main push-run statuses observable, resolve the repository PR-creation setting or provide an approved scoped token, then reassess source development from this verified main.

Verified main commit: `69ac1afcab987c92de252f94793fafb2b66474be`
Verified main tree: `1ad128e83fda57fe1288b59004f1a044040c959d`
Latest segment: `work/construction/segments/0308-verify-hosted-automation.md`
Sequence: 308
Latest segment SHA-256: `e7a71860e077e255b4d175d4e048d8a6479f745c132b3ac9e059dbd201590e2f`
