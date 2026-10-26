# Sequence 733: use argument arrays in the CI self-check

The CI self-check now validates fixed nonempty argument sequences and calls `subprocess.run` with `shell=False`. Its regression asserts every invoked argv and the shell-disabled/check-enabled flags. The focused test passed 2/2; compile and targeted mypy with imported modules suppressed passed. The normal strict import-following mypy invocation surfaced two existing unused-ignore diagnostics in `sentientos/admin_utils.py`, with no diagnostics in the changed script.

Tested code-only tree: `a2045c483adba37107ecfcb1be734ba5433a4070` from verified main `adfcad083829f0c960f3244379ccef8d701ff7db` / `cd9240aa8bd6184d00c84f34ddc5fdc9af561f17`.

Evidence record: `work/construction/evidence/0733-use-argv-ci-self-check-commands.json`
Evidence SHA-256: `e04bb605681ee6e188aee596b38621433634954d0c90c09916e7b07f5dbc1396`
