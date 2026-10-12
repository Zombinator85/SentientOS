# 0074 — Restore frozen custody and verify exact candidate publication

Source: `00023a269a2f3a0ebb08334a53465a57e2849702`, tree `6b71895e08991788ee78fe19acd726b69226e668`.

The exact original journal blob 5127025527ec6248a159b228b6929a196f1449d1 was recovered from Git history. Current journal bytes were its exact 586,585-byte prefix plus a 6,968-byte suffix. Segment 0073 preserves that suffix verbatim, including diagnostic details not copied word-for-word into segments 0069–0072. The original index is preserved as evidence before correction. The journal is restored only after proving the split/recombination identity.

Index repair removes the duplicate navigation entry for sequence 65 and binds unchanged segment bytes to their actual digests/predecessors. The mismatched older hash claims in the original index remain diagnostic evidence: source 37551706 contains current segment 43 bytes, not the stale claimed predecessor; source f983c53e has no segment 65 path. No lost older bytes were invented. Historical segment files are unchanged.

The existing construction preflight now validates every changed candidate Git-tree member against tested bytes and SHA-256/Git identities, compiles exact Python bytes, verifies frozen journal and checkpoint custody through the same verifier, rejects changes to historical segments or frozen metadata, and requires actual remote-blob readback before ref-update readiness. The publisher still performs separate expected-HEAD CAS and exact tree readback.

Focused tests cover valid continuation, unexpected append, digest/remote mismatch, staged corruption hidden by restored disk bytes, missing predecessor, duplicate sequence, stale checkpoint binding and invalid Python bytes. No privileged acceptance or runtime authority changed.

Next: settle the existing loaded-code evidence boundary, then advance independent durable-source reconstruction and objective developmental scoring.
