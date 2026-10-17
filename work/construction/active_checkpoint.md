# Active construction checkpoint

Sequence 301 closes the first-create durability gap in work-plan execution journals: descriptor-bound private-directory creation now synchronizes every new parent entry before opening and appending the journal. Executor regressions prove an unsynchronized directory blocks task effects and work-run persistence while exact bytes recover as interrupted. Canonical local runner passed 36/36 affected tests on exact source `92ec10a9cf2b22aa640cc702877642731723cb06` (tree `e1635bdc4f6beb62362991d19f140066bb6501e3`); acceptance, targeted Mypy, compilation, and diff checks passed. GitHub-hosted CI, source validation, docs/linkcheck, Helm, invariants, and the actual-Administrator Required Quality Gate all passed on the same source identity.

The sequence-286 provenance limitation remains: nine known deleted payloads and one unidentified deleted payload are unrecoverable. No historical payload was reconstructed or omitted.

Next dependency: give the scheduled federation-health workflow legitimate Administrator authority for protected-state reads while preserving explicit approval and write-scope boundaries, and fail closed when privilege is unavailable.

Verified local source commit: `92ec10a9cf2b22aa640cc702877642731723cb06`
Verified remote source commit: `92ec10a9cf2b22aa640cc702877642731723cb06`
Verified source tree: `e1635bdc4f6beb62362991d19f140066bb6501e3`
Latest segment: `work/construction/segments/0301-first-journal-directory-durability.md`
Latest segment SHA-256: `91989f7a22ab71829a97894c3be287a5b155dba04f297358e3c56bdb63a9a600`
Latest evidence: `work/construction/evidence/0301-first-journal-directory-durability.json`
Latest evidence SHA-256: `63b196fcbf39bd578281cdb8a1c3b07262f7488ec299191e64e07318e631c7a3`
Sequence: 301
