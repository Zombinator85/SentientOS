# Active construction checkpoint

Sequence 299 proves that a child process can exit after a partial production journal append, releases its kernel lock, and leaves incomplete bytes intact for fail-closed rejection. Seven affected suites passed 58/58 with canonical `scripts.run_tests` on local source commit `d8ecf0a4805b10c396e44288ebe3b50a5c1d7966`; targeted Mypy, compilation, diff checks, and custody passed. Remote source `14513d80af2437f4603e838959577758658eb904` has the same tree `c1249b9cc0df24727d7fe02e7ef0b37dd3191826`; its full CI, invariants, and actual-Administrator quality gate passed.

Latest verified main: `24fb96724b44f544ecf5fdadad0da8b0b31b9fa5`, tree `f174b6936415e06c671e42f0de809fb128bb9578`. Its full CI, Required Quality Gate, invariants, Docker, Codex CI, and Docs Deploy passed.

Next dependency: fsync the execution-journal directory after writing and syncing a new start record, and fail closed if directory durability cannot be confirmed.

The sequence-286 provenance limitation remains: nine known deleted payloads and one unidentified deleted payload are unrecoverable.

Verified local source commit: `d8ecf0a4805b10c396e44288ebe3b50a5c1d7966`
Verified remote source commit: `14513d80af2437f4603e838959577758658eb904`
Verified source tree: `c1249b9cc0df24727d7fe02e7ef0b37dd3191826`
Latest segment: `work/construction/segments/0299-partial-append-process-crash.md`
Latest segment SHA-256: `19b4fa6b7535e10287b5a9619422055cb8d24f99ce2ebb20411abc2e16ecb6bd`
Latest evidence: `work/construction/evidence/0299-partial-append-process-crash.json`
Sequence: 299
