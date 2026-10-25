# Sequence 675: Require canonical paths for v2 shards

The v2 custody verifier checked shard digests and predecessor order but accepted any safe repository path as the descriptor's shard path. It now requires the exact sequence-derived path under `work/construction/shards-v2/`, binding directory, shard number, and sequence range to the descriptor. A tampered descriptor that points at another in-repository file is rejected even if that file is readable.

The focused custody/publication suites pass 28/28, including a path-rebinding regression. Custody verifies through sequence 674, Python compilation and diff checks pass, and the pre-append candidate source guard passed on the exact staged tree. The documentation build generated 616 pages for this candidate family. No external publication was attempted; frozen v1 files remain unchanged.
