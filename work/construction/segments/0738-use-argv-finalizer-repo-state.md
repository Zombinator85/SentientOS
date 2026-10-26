# Sequence 738: use argv for finalizer repository-state commands

The finalizer now invokes fixed `git status` and `git diff` operations with argv and shell interpretation disabled. Tracked-change collection preserves the prior short-circuit behavior when the cached diff fails. Three focused regressions and the full legacy finalizer test selection passed; compile and targeted mypy passed.

Tested code tree: `d8087dcb58babcc3e516299cc4a7434027378880` from verified main `f6ce2d8ab3d2d603f616dce5b847bd6470e313c9` / `5ab5b98b58f6c483801a6d5722bdb9641775d649`.

Evidence record: `work/construction/evidence/0738-use-argv-finalizer-repo-state.json`
Evidence SHA-256: `48ffdd891dc37cbc2e218b629629da245a524aa98c97be3248a97d8874943dac`
