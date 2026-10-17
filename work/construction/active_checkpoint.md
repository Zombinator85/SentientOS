# Active construction checkpoint

Sequence 304 confirms PR #2282 merged through a standard merge commit. Main is `505c42ce4f80694e8b99b648eb9bdf1e1ba756b2`; GitHub compare shows its tree exactly matches the verified candidate tree `8450d45dd76699b76a4102b4fadda14b5a67a4a1`. The final-tree hosted gate passed all 23 required acceptance nodes, strict audit and immutability as UID 0, and the unchanged privileged finalizer returned `ready_for_pr_metadata`. Full CI, Docker, invariant, and related workflows passed before merge. Exact hosted evidence is retained in sequence 304.

The sequence-286 deleted-payload limitation remains: nine known payloads and one unidentified payload are unrecoverable. No historical payload was reconstructed or omitted.

Next dependency: observe the scheduled federation-health updater on `main`, then verify its actual Administrator execution, retained authorization, and documentation-only commit scope.

Verified main commit: `505c42ce4f80694e8b99b648eb9bdf1e1ba756b2`
Verified main tree: `8450d45dd76699b76a4102b4fadda14b5a67a4a1`
Latest segment: `work/construction/segments/0304-verified-hosted-landing-integration.md`
Sequence: 304
Latest segment SHA-256: `2ccdd4dc82e312d0bbb4fa98282460a1959b7c84eb0f8b67a5026c16730acbfa`
