# Sequence 346: scope post-merge feedback comment authority

## Source change and candidate verification

After repeated post-merge failures, the feedback workflow first declared only `issues: write` for its fixed `issues.createComment` step. The job still ran only for a closed merged PR, did not check out PR content, and a regression asserted the narrow permission. Candidate `c160273582ef5592148b4176d532e4992738f277`, tree `52d055c609a6a4fdf917c40e9c95318969f27450`, merged normally through PR #2336 as main `e5a19f3a7bb6184395499857acdb4d136e7e8e82`, preserving the prior candidate commit. Local exact source commit `7cb20b7b79863dc5682d6e48da6918ef8deea36a` has the same tree.

Candidate CI runs `39093828567` and `39093825293`, Required Quality Gate `39093828540`, Docker `39093828534`, invariants `39093828517`, Codex CI `39093828536`, Lint Benchmark `39093828533`, Release `39093828529`, and Gradient `39093828571` passed. QG completed hosted Administrator, strict audit, immutability, exact 29-node acceptance, and finalizer checks; QG artifact `12124180418` has digest `ef77b1e28adbda492c068ab7363ee2f328baa4cd51bc18451d635669dbcc3082`, finalizer artifact `12124235358` has digest `0b3395790d48e72a66bf67845427d52f912566428ef7d6c8b0ec1c5b4a273cec`.

## Post-merge finding

Main `e5a19f3a7bb6184395499857acdb4d136e7e8e82`, tree `52d055c609a6a4fdf917c40e9c95318969f27450`, passed CI `39094096429`, QG `39094096400`, Docker `39094096521`, invariants `39094096444`, Codex CI `39094096533`, and Docs Deploy `39094096404`; Forge Smoke `39094096473` was skipped by workflow conditions. QG ran as UID 0 and bound the exact main SHA/tree; its artifact `12123732078` has digest `e8199470f6973f88a87d0555217ad5ae31dadd806b5aa96aa26b5fe81a698d00`.

The real post-merge feedback run `39094096527` still failed. Its token log showed `Issues: write`, yet GitHub returned HTTP 403 `Resource not accessible by integration` for the pull-request comment. Therefore the first permission choice did not repair the workflow. Sequence 347 narrows the job to `pull-requests: write`, the PR-specific scope, and validates it with another real merged run.
