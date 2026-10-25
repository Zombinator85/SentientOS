# Sequence 681: reject boolean construction custody byte counts

A targeted probe demonstrated that the verifier accepted JSON `true` for a legacy-journal byte count and a segment byte count when the referenced content was exactly one byte. The verifier now requires exact JSON integers for both fields. Regression coverage proves both custody rejection and candidate-publication rejection; malformed records fail closed before a candidate can be published.

The focused custody and candidate-publication suite passed 43/43. Continuation custody verified through sequence 680 with no failures. Mypy baseline reported zero new errors and an overall baseline improvement. No documentation surface changed, so a local documentation build was not required; hosted CI for the prior integration candidate is still running its post-merge docs/linkcheck job.

The tested code-only tree is `986a689646c3cd5217abfef3a014db96a3064ed5`, based on verified main `6e7d7e3c375cccbd90ea2ca08f27cf8bba5970d9` / `431dd718bb8398f3deac7259879760fe337146b5`. Its source preflight reported `candidate_integrity_ready_for_blob_upload` with no failures. The frozen v1 index, original checkpoint, all prior v2 shards, segment history, and predecessor bindings remain unchanged.
