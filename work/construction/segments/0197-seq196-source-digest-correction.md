# Sequence 197 — Correct the source digest in restart evidence

Starting HEAD: `c15f9a3d50b47214dc534d080e1ec8909ad7c22d`, tree `df01d1a74577bc80999a05a0cfbefdaa5470b285`.

Independent readback of the published sequence-196 test blob and execution of that exact artifact found that its evidence `source_paths[0].sha256` value was computed incorrectly. The source blob identity remains `88bf9765bbc9574a64f62c81e63957fd1b75f57a`; the correct SHA-256 of its downloaded UTF-8 bytes is `d3cb41d0284d05869859734561f97de59a664e4ba13723b413edc91dd7068630`. The earlier sequence-196 evidence object is preserved unchanged; this append-only record supplies the corrected digest and the independent verification result.

The exact published source artifact passed `test_admitted_embodied_consequence_conditions_later_strategy_comparison` (1 passed) in a fresh test-file copy. Compilation passed. A separate local equivalent passed the same node, compileall, and diff check.

This correction changes evidence custody only. Sequence 196 remains partial: multi-event vector feedback lacks its own World-State projection/admission, and the fresh interpreter builds a new fixture proposal without governed inference.
