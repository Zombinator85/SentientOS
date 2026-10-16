# Active construction checkpoint

Sequence 295 hardens append-only work-plan journal I/O. Recovery rejects oversized content before reading it, opens only regular no-follow files, verifies descriptor identity, and reads no more than the configured limit plus one byte. Appends use no-follow descriptor operations and check file identity and capacity before writing. The journal event schema and hash chain are unchanged. Four regressions cover oversized recovery, growth past the bound before append, symlink reads, and a symlink append target that must stay unchanged. The focused suites pass 34/34, with no skips or failures; compilation, Mypy for the changed module, custody verification, and diff checks pass.

The exact verified local source is `c0a6bdfa24605b04632bc137cbba4e0ac0b8fc7e`; its remote equivalent is `86272401cbb15d2503a45860634bbb068642ce6f` with tree `f2b27d03bf58a4f289a4dbb961f65a9e27f2ffea`. CI, Required Quality Gate, and Invariant Tests passed. Gate artifact `12078982143` was independently read back with GitHub's matching digest and confirms effective UID 0, Administrator authority, exact source/tree, unchanged source and repository identity, strict audit, and immutability.

Next dependency: ensure concurrent or stale journal writers cannot fork the append-only hash chain or exceed the byte cap.

The sequence-286 historical provenance gap remains: nine known payloads and one unidentified payload are unrecoverable.

Latest verified main: `d9fbac78dad9187065fcdeaf112bf641cf3508ea`
Latest verified main tree: `71d300a7ddd35343b710e3e52b58e4b02962825a`
Verified local source commit: `c0a6bdfa24605b04632bc137cbba4e0ac0b8fc7e`
Verified remote source commit: `86272401cbb15d2503a45860634bbb068642ce6f`
Verified source tree: `f2b27d03bf58a4f289a4dbb961f65a9e27f2ffea`
Latest segment: `work/construction/segments/0295-bounded-journal-io.md`
Latest segment SHA-256: `17ada774f299312f94c789470b9e66c4efdc6f9afcc275910aecfdf11ab238ab`
Latest evidence: `work/construction/evidence/0295-bounded-journal-io.json`
Sequence: 295
