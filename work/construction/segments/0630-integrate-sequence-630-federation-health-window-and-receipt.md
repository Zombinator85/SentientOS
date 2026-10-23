# Sequence 630 — integrate large-window fix and Federation Health execution

Sequence 630 records the sequence 630 Federation Health arithmetic fix, its normal merge, exact-main hosted verification, the subsequent Health execution, and the publisher's receipt merge.

The source defect was that a valid positive `--hours` value could exceed Python's `timedelta` range and raise `OverflowError`. The fix treats such a window as including every representable timestamp by using the minimum representable UTC datetime as the cutoff; it introduces no arbitrary cap. The no-legacy-skip regression is registered in hosted source-validation acceptance. Parsing behavior, local-snapshot labeling, and authority boundaries remain unchanged.

PR #2716 candidate `dac402df86d518cf7048924e28e7aeaa2e355871` (tree `74e407056a2e0777633b704d7b52ada57a9ffef9`) was based on `1cfaa8609d18db66c3d1cae7b3c4b550cad006d2` and merged normally as `04a37791013b598241a5204525d18a542d2281cd`, preserving the candidate as its second parent and retaining the same source tree.

The exact candidate passed Required Quality Gate #39996927733, including strict hosted Administrator audits, exact acceptance, the privileged landing finalizer, and the separate pre-publication metadata guard. PR CI #39996927789 and same-SHA push CI #39996912242 passed. The source-validation step explicitly ran the large-window arithmetic regression; Mypy, pytest, docs linkcheck, and Helm/Kubernetes passed. Invariants #39996927738, Docker #39996927775, lint #39996927716, Codex CI #39996927732, Release #39996927904, and Gradient null regression #39996927996 passed.

On exact source main `04a37791013b598241a5204525d18a542d2281cd` (tree `74e407056a2e0777633b704d7b52ada57a9ffef9`), Required Quality Gate #39997722316, CI #39997722005, Invariants #39997722313, Docker Image #39997722311, Codex CI #39997721915, Docs Deploy #39997721935, and Nightly Self Check #39997721969 passed. Forge Smoke #39997721954 was skipped by workflow conditions. CI source validation and the full self-check passed.

Federation Health Update #39997721950 ran on that exact main commit. Hosted Administrator availability, report generation, receipt binding, and artifact publication passed. The report truthfully states one configured node, zero events in the previous 24 hours, a latest local event at `2025-06-05T16:25:13.805813Z`, and stale status. Its source is the configured local log snapshot, not live federation telemetry. Report digest: `e6a98f8e9d89cc626eb6a329fb9c0c26d289f8de6200db37a577044ca793959c`.

The repository App publisher opened PR #2717 with only `docs/FEDERATION_HEALTH_EXECUTION.json`. Candidate `314dcad0270ffa26840908ff16bff4e8bb625877` is based on `04a37791013b598241a5204525d18a542d2281cd`; its receipt binds run #39997721950, source SHA `04a37791013b598241a5204525d18a542d2281cd`, successful hosted Administrator preflight and report generation, and the report digest. It merged normally as `0b34c1d7756dd1d6e0bf03ebe6df7080495b3ab0`, tree `faf3320ef3f4c41184709f67c6a129b44dc65cc4`, first parent `04a37791013b598241a5204525d18a542d2281cd`.

PR #2717 exact-candidate Quality Gate #39997779654 passed strict hosted Administrator audits, exact acceptance, hosted finalization, and the separate metadata guard. PR CI #39997779468 and same-SHA push CI #39997776005, Invariants #39997779560/#39997776026, Docker #39997779557, lint #39997779605, Codex CI #39997779536, Release #39997779540, and Gradient #39997779507 passed.

On current main `0b34c1d7756dd1d6e0bf03ebe6df7080495b3ab0`, Required Quality Gate #39998777779, CI #39998777660, Invariants #39998777532, Docker Image #39998777411, Codex CI #39998777501, and Docs Deploy #39998777604 passed. CI completed source validation (including the large-window regression), Mypy, pytest, documentation linkcheck, and Helm/Kubernetes. Forge Smoke #39998777370 was skipped by workflow conditions. The receipt-only merge does not alter the source tree or assert that the stale local snapshot is live telemetry.

Sequence 630 follows `segment-sha256:d251a8c2adab460d675746018872915ea85d56e54995bd9ee32daa54f13ebe46`.
