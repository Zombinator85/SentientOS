# Active construction checkpoint

Sequence 293 makes validated adverse work-run outcomes affect canonical task plans. The planner reconstructs the latest schema-v3 run, plan evidence, and append-only task journal, then binds both the prior run digest and journal head into plan evidence. Failed or partial outcomes suppress destructive apply for review; legacy/unbound history is treated as unknown and gates apply. The affected suites pass 62/62. CI, the privileged Administrator gate, and invariant tests pass on remote source `06e80aa80dd32a301437b3204fa3ed9a6b06c039` / tree `9a66f2e292581dd5298443e66c4d662f88e5a282`. Gate artifact `12078871501` was read back with matching digest and confirms UID 0 Administrator, strict audit, immutability, and unchanged exact source.

Sequence 292 is also fully green through its evidence head.

The sequence-286 historical provenance gap remains: nine known payloads and one unidentified record are unrecoverable.

Latest verified main: `d9fbac78dad9187065fcdeaf112bf641cf3508ea`
Latest verified main tree: `71d300a7ddd35343b710e3e52b58e4b02962825a`
Verified local source commit: `32ad587ddf6d35dc568a3bb5cb9dfbd25a340f61`
Verified remote source commit: `06e80aa80dd32a301437b3204fa3ed9a6b06c039`
Verified source tree: `9a66f2e292581dd5298443e66c4d662f88e5a282`
Latest segment: `work/construction/segments/0293-reconstruct-adverse-outcomes.md`
Latest segment SHA-256: `decb52a0ca53502c65f9c83fafd4b1c54a7336cd7d41b044c1841c8b609d46f9`
Evidence: `work/construction/evidence/0293-reconstruct-adverse-outcomes.json`
Evidence SHA-256: `9e982cf7696bc44efe454583c3b21b0d83100778c9b45b61056820850a9dc002`
Sequence: 293

Next: prove a clean journal-backed review cycle changes the later plan predictably after adverse history without weakening execution or apply authority.
