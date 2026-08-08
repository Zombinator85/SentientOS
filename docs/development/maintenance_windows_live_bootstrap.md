# Windows live maintenance bootstrap

The live bootstrap is an inert composition layer over the existing activation profile, maintenance-loop activation, health probe, candidate collector, autonomy cycle, wake cycle, Windows host-readiness, and Windows deployment APIs. It does not create a scheduler, execute a wake, invoke Codex, mutate Git, or inspect/create credentials.

## Operator flow for `C:\SentientOS`

1. Run `inspect-host --repository-root 'C:\SentientOS'`. This delegates executable discovery to the existing read-only host readiness inspector; Python, Git, Codex, and PowerShell paths are returned as facts. Missing Codex is reported and never fabricated, and authentication remains `unverified`.
2. Run `write-template`, then fill and approve that one closed manifest. Authority classes, allowed paths, budgets, validation expectations, publication mode, scheduler policy, and the dedicated canary boundary are operator decisions—not host discoveries.
3. Run `render` with the manifest and saved inspection result. Add `--create-custody-directories` only to create missing empty custody directories. Existing custody is preserved; conflicting artifacts block and nothing is deleted or reset.
4. Run `verify` on the bundle index with a current UTC evaluation time. Verification uses the production component validators and checks artifact digests and cross-component bindings without running maintenance.
5. Print (do not execute automatically) the bounded preflight sequence, run the existing canary, require `canary_completed`, verify deployment, and only then use the printed existing Task Scheduler installation command.

The manifest derives `activation`, `state`, `workspace`, `scratch`, `inbox`, `signals`, `collector`, `cycle`, `wake`, `logs`, `deployment`, and `configuration` beneath its explicitly external custody root. The layout grants no authority. All custody must remain outside `C:\SentientOS`.

The canary source, exact validation node, and allowed-path boundary are independently visible in the manifest and bundle index. Any broader standing maintenance paths remain a separate explicit grant. Persistent configs retain their schema-required fallback time; printed wake/readiness argv uses a fresh runtime UTC placeholder.

## STOP-first rollback

Create the existing external STOP marker before intervention or scheduler removal. Preserve every existing custody directory, receipt journal, deployment artifact, and log. Never reset or delete custody as rollback. Inspect receipts and resolve the STOP condition under operator authority before resuming.
