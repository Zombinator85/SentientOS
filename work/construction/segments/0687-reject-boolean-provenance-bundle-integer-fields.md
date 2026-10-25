# Sequence 687: reject boolean provenance bundle integer fields

The previous verifier accepted a valid provenance bundle when the manifest used `schema_version: true`. Direct checks against verified main also showed `bundle_window.count: true` passed the prior integer validation. The verifier now requires exact JSON integer types for integer-typed manifest fields; a regression archives both boolean values and confirms the bundle verifier rejects them.

The tested code-only tree is `ed4dd8618ad2e6889c27b19183d9ec58bf57bea9`, based on verified main `427a6f7339e8a2d1e2a887e72182050e006370f8` / `aef5943ebd550def1043556caf73dc5e64336991`. The exact regression passed through `scripts.run_tests`; targeted mypy found no issues in the verifier. Only `scripts/verify_test_provenance_bundle.py` and `tests/test_provenance_bundle_scripts.py` changed. Documentation is unaffected.
