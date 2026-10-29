# Sequence 1012: scope repeated strict linkcheck to changed repository link targets

Based on the verified sequence 1011 linkcheck investigation, keep the strict Sphinx check on every pull request. On main pushes, first compare the pushed commit range against every blob/main and tree/main link in the documentation. Repeat the same strict linkcheck only when one of those linked targets changed. If source parsing or commit comparison is unavailable, the selector fails closed and runs the strict check. The documentation build and all other CI jobs remain unchanged.

The CI docs checkout now fetches two commits so a normal single-commit push can compare its base and head. A focused workflow contract test verifies the PR condition, push comparison inputs, unconditional make docs, and target-path matching for files and directories. Four focused tests, targeted mypy, lock verification, and git diff --check passed. The full hosted PR and post-merge workflows remain the integration acceptance.
