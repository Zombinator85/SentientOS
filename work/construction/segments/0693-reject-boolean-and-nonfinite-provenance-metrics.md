# Sequence 693: reject invalid numeric provenance metrics

The test provenance trend analyzer used Python's `isinstance(value, (int, float))` for numeric metrics. Because JSON `true` is an integer subclass in Python, a run with `tests_executed: true` and `tests_passed: true` was incorrectly included as a complete successful run. Non-finite numeric values could also contaminate trend summaries, and extremely large integers could raise during conversion.

The numeric reader now rejects booleans, non-finite values, and values that overflow float conversion. The regression supplies boolean counts, NaN/infinity rates, and an oversized integer; it proves the malformed run is excluded and invalid metrics contribute zero. The new targeted test is explicitly exempted from the legacy test quarantine so the repository test runner executes it.

The tested code-only tree is `a80f079479fa19609642af1e5f12f87aaccf6ea7`, based on verified main `4cb5b1bdd7c10b16da16ed969fe796a9c4219f53` / `742d0e0b30c1efb08b7994ab0be360a2992722ed`. The focused regression passed; targeted mypy on the changed source passed. Documentation is unchanged. The v1 anchor and all earlier v2 shards remain unchanged.
