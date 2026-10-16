## 2026-10-13 checkpoint — validate restored fixture receipts and reject custody tampering

- Continued from freshly verified source commit `08ba1cf4494cad863beaffd9a464ab4c4185e5e8` / tree `bd3e132c8fc619e82ce0d6e799299b6d247a41c8`.
- The fresh-process task-family episode now validates each serialized invocation receipt with the repository's `validate_receipt()` canonical producer/verifier contract before owner construction. The fixture issuer's receipt index is reconstructed from those verified serialized dictionaries.
- Added a tampering control that changes the receipt-custody bytes while retaining the original custody digest. The child rejects the data at the bounded read/digest gate before it imports the test module or constructs a cognition owner.
- The fixture episode and adverse/control outcomes remain unchanged. These tests verify test-fixture evidence custody; they do not verify a production receipt journal or an actual local-model backend.

Checks on the published source:
- Focused fresh-process acquisition/transfer, current-context isolation, adverse-example, and progression cases: 4 passed.
- Python compilation, UTF-8 decoding, NUL scan, and trailing-whitespace scan passed.

Source commit: 2b2ae568dfb03a14870fcd3cb29dd200830c557f
Source tree: d7b89eba9430202ce5c1a2896884d7e2eb73751d
Changed test blob: d522b6e970c3180ea863f293c1824b2b24638fc8
Construction remains unverified for production.

Next: inspect and, where supported by existing owners, replace the custom fixture receipt sidecar with the canonical persisted-receipt verification path in a fresh process. If that requires real serving authorization or backend invocation, preserve the dependency and continue with nonconsequential source-backed controls.
