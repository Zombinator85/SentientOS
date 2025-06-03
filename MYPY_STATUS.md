# mypy Status

Current run: `mypy --ignore-missing-imports .`

- Total errors: 180
- Legacy modules: 150
- Need fixes: 50
- Safe to ignore: 19

Legacy modules are older CLI tools without type hints. Contributors are welcome to
help migrate these. The "need fixes" category covers real mismatches mostly in
`multimodal_tracker.py` and `music_cli.py`. The "safe to ignore" errors come from
dynamic imports and will be suppressed once stubs are added.

### Call for Contributors
If you want to help reduce the error count, pick an item from the "need fixes" list
and submit a pull request. See `CONTRIBUTING.md` for our ritual checklist.
