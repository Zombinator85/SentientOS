# Sequence 669: Correct documentation root-link check

The exact-head Required Quality Gate for PR #2768 passed, including hosted reconstruction, privileged landing finalization, and metadata guard. The CI documentation build itself passed, while its strict Sphinx linkcheck failed on one cross-reference: `../../AGENTS.md` resolves outside the Sphinx source set and was reported as an unknown source document. The template now refers to the repository's `AGENTS.md` as inline code, leaving the canonical bootstrap-contract link intact.

The focused doctrine documentation regression passed 4/4 with run ID `4e05e496674f497da8873cb548fd8a8a`; its provenance artifact is held in `/tmp/sentientos-seq669-test-runs/test_run_provenance.json` with SHA-256 `15c210d5efbc755985e4452897f55af0a6a347b61f53d904737274b4f9bcbfba`. The local 616-page docs build passed after the edit. The hosted linkcheck and all required exact-head CI must pass on the updated PR head before merge.

PR #2768 remains open and unmerged while this correction is prepared. Evidence: `work/construction/evidence/0669-correct-documentation-root-linkcheck.json`.
