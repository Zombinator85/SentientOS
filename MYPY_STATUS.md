# mypy Status

Current run: `mypy --ignore-missing-imports .`

- Total errors: 145
- Legacy modules: 130
- Need fixes: 40
- Safe to ignore: 18

Legacy modules are older CLI tools without type hints. Contributors are welcome to
help migrate these. The "need fixes" category covers real mismatches mostly in
`multimodal_tracker.py` and `music_cli.py`. The "safe to ignore" errors come from
dynamic imports and will be suppressed once stubs are added.

January 2026 update: `log_json` now enforces required fields, paving the way for
cleaner typing of log utilities. Error counts remain but are easier to address.

February 2026 update: legacy modules have been typed or quarantined. Central
schemas ensure new code passes strict checks.

March 2026 update: adopting the centralized logger trimmed the error count to
145. Several utilities gained type hints and tests were refreshed.

### Call for Contributors
If you want to help reduce the error count, pick an item from the "need fixes" list
and submit a pull request. See `CONTRIBUTING.md` for our ritual checklist.
