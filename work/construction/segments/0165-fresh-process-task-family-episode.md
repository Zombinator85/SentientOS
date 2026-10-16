## 2026-10-13 checkpoint — execute task-family transfer after a fresh process restart

- Continued from freshly read branch checkpoint `ab95b9fe7a2fa93d3fb8ef96811d8c18f60bbe1b` / tree `64c0817a95f928805bd5de5286064b23b9f14113`.
- Extended the existing fixture episode test so the second held-out request is executed by a separate Python interpreter. The child reopens the staged request and durable developmental-history/admission roots, reconstructs a new composition owner and fixture invoker, and receives only canonical serialized fixture receipt data bounded to 4 MiB and bound by a SHA-256 custody digest. It does not inherit the parent process's owner, invoker object, receipt dictionary, or run objects.
- The new child episode reads the source-bound task-family examples through the admitted history path. Controls preserve the history-present, withheld, and restored split. The deterministic fixture scores present 3/3, withheld 0/3, and restored 3/3, while the progression remains descriptive and does not assert learning or performance improvement.
- Added negative packet-projection checks showing that an example with a substituted score digest or a source digest that conflicts with the selected source is omitted. Existing adverse examples remain adverse.
- The receipt verifier and inference issuer in this experiment remain test fixtures. This demonstrates fresh-process fixture composition and retained-state handoff, not real-model acquisition, authentic production receipt verification, or improved cognitive performance.

Checks against the published source bytes:
- Focused acquisition/transfer, withheld/restored, adverse-example, and bounded progression group: 4 passed.
- `python -m py_compile sentientos/resident_developmental_cognition.py tests/test_resident_developmental_cognition.py`: passed.
- UTF-8 decode, no-NUL and trailing-whitespace checks for the changed test file: passed.
- No production behavior or local-model learning is claimed.

Source commit: 08ba1cf4494cad863beaffd9a464ab4c4185e5e8
Source tree: bd3e132c8fc619e82ce0d6e799299b6d247a41c8
Changed test blob: abbe7fe19849daa73994e786157bd854e90518cd
Construction remains unverified for production.

Next: add a fresh-process negative control that rejects tampered persisted fixture receipt custody before owner recovery, then continue toward an acquisition-and-transfer run driven by the real admitted owner path. Keep fixture effects and actual-model evidence separate.
