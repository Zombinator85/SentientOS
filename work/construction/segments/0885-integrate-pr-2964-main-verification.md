# Sequence 885: integrate PR 2964 main verification

PR #2964 merged as `3ac460e9ca2e2602b4b76c7c9e0a77323ad980fc` with verified tree `319a105b01b00be9eb462cd833a2ad080bd31df1`. Its exact candidate was `2037d1829e7828cbcd315834cc34d18c8a2ba882`; the candidate tree matches the merge tree. The final hosted PR checks passed: CI (40547707663), Codex CI (40547707921), Docker Image (40547707869), Lint Benchmark (40547707859), Invariant Tests (40547707956), Gradient null regression (40547707606), Release (40547707709), and Required Quality Gate (40548247012). The earlier Required Quality Gate run (40547707781) failed before reconstruction because the PR title differed from the exact commit subject; after the title was aligned, the rerun completed successfully.

Remote `main` readback and source preflight match `3ac460e9ca2e2602b4b76c7c9e0a77323ad980fc` and tree `319a105b01b00be9eb462cd833a2ad080bd31df1`. Post-merge workflows succeeded for CI (40548893573), Codex CI (40548893490), Docker Image (40548893403), Required Quality Gate (40548893555), Docs Deploy (40548893473), and Invariant Tests (40548893494). CI documentation build and warnings-as-errors linkcheck both passed. Forge Smoke (40548893352) was skipped by its workflow condition.

GitHub tree readback verified exact blob identities for the current v3 head, active checkpoint, sequence 884 evidence and segment, and seventeenth immutable v3 shard. Custody verified all 884 predecessor sequences before this append. The v3 head was 1373 bytes before this append; this append adds one immutable predecessor-linked shard and updates only the bounded head and active checkpoint.

Evidence record: `work/construction/evidence/0885-integrate-pr-2964-main-verification.json`
