# Sequence 683: reject boolean checkpoint sequences in the frozen history anchor

A targeted malformed-history probe showed that the v2 reader accepted `true` as the anchor checkpoint sequence when the frozen v1 anchor contained one segment. The verifier now requires the anchor binding value to have exact JSON integer type before comparing it to the anchor segment count. A regression test rebinds the anchor digest and Git blob identity around the malformed bytes, then confirms custody rejects the boolean value.

The focused construction custody and candidate-publication suite passed 44/44. Before appending this record, continuation custody verified all 682 existing segments. The mypy baseline reports zero new errors and overall improvement. The documentation surface did not change. The frozen v1 index and original checkpoint, all prior v2 segment bytes, shards, predecessor bindings, and checkpoint invariants remain unchanged.

The tested code-only tree is `275ef3ea3b3fdcd72b1ade88d64cc99120c6ca15`, based on verified main `fef16ad78303c7acacecc5ed52cadc7cbf30a623` / `13152da5c2dd37f38cc7874863ddcb62781aa2b1`.
