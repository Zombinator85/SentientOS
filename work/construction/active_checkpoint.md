# Active construction checkpoint

Sequence 300 makes work-plan journal appends directory-durable: the record is fsynced before its containing directory while the writer lock remains held, and a directory-sync failure leaves the journal recoverable as interrupted without claiming success. The canonical runner completed seven affected suites 60/60 on local source `c90f244b5637c1bb67eb230cbadef7860e10af30`; exact-node acceptance, targeted Mypy, compilation, diff checks, and custody passed. Remote source `b49176f299120b1edc95be207eb0865e4e82193d` has the same tree `252d8ce632446ea7771934ffcdfbe36b2ebf399d`, parented by verified main `7743ea61b14e6f23d01485c1fa679db5cc2036ce`. Its actual-Administrator gate, invariants, and source validation passed; the gate artifact confirms UID 0, strict audit, immutability, and unchanged source/repository identity.

The sequence-286 provenance limitation remains: nine known deleted payloads and one unidentified deleted payload are unrecoverable. No historical payload was reconstructed or omitted.

Next dependency: test at the executor boundary that journal directory-sync failure blocks task effects, and prove fresh journal-directory creation syncs every parent entry.

Verified local source commit: `c90f244b5637c1bb67eb230cbadef7860e10af30`
Verified remote source commit: `b49176f299120b1edc95be207eb0865e4e82193d`
Verified source tree: `252d8ce632446ea7771934ffcdfbe36b2ebf399d`
Latest segment: `work/construction/segments/0300-work-plan-journal-directory-durability.md`
Latest segment SHA-256: `cebe42b8cbea90e5ea43d02587dc72379be1c1da9083c7fb3be778c41144e756`
Latest evidence: `work/construction/evidence/0300-work-plan-journal-directory-durability.json`
Latest evidence SHA-256: `327f136eed9a1b84ca7aac79c90e10536b0b83d9e274fa083f2f56225f95a70d`
Sequence: 300
