# mypy Status

Current run (2029-06-10): `mypy --strict privilege_lint scripts/auto_approve.py`

- Total errors: 0
- Legacy modules: 0
- Need fixes: 0
- Safe to ignore: 0

Legacy modules are older CLI tools without type hints. Contributors are welcome to
help migrate these. The "need fixes" category previously covered real mismatches
mostly in `multimodal_tracker.py` and `music_cli.py`, which are now typed. The
"safe to ignore" errors come from dynamic imports and will be suppressed once stubs
are added.

January 2026 update: `log_json` now enforces required fields, paving the way for
cleaner typing of log utilities. Error counts remain but are easier to address.

February 2026 update: legacy modules have been typed or quarantined. Central
schemas ensure new code passes strict checks.

March 2026 update: adopting the centralized logger trimmed the error count to
145. Several utilities gained type hints and tests were refreshed.

April 2026 update: "Type-Check & Audit Remediation" triaged about 180 remaining errors. Core modules and workflows now conform to the log schema, and new audit tests guard against regressions.

April 2027 update: current run reports **115** type-check errors.

May 2027 update: `presence_ledger.py` and `presence_analytics.py` have been fully annotated and are now mypy-clean (removed from need-fixes list). **Total errors down to 115.**

April 2029 update: core modules run with `mypy --strict` and report **0** errors.
All remaining `type: ignore` usages carry inline comments explaining the reason.

June 2029 update: `privilege_lint` and `scripts/auto_approve.py` checked clean
with `mypy --strict`. A stub ignore comment was added for the optional `yaml`
import and the `scripts` folder is now a package to prevent duplicate module
errors.

### Call for Contributors

If you want to help reduce the error count, pick an item from the "need fixes" list
and submit a pull request. See `CONTRIBUTING.md` for our ritual checklist.

March 2028 update: manual sweep added comments to all `# type: ignore` lines for clarity.
