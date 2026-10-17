# Active construction checkpoint

Sequence 322 protects `sentientos_data/vow/**` from automatic finalizer cleanup and includes content digests for those paths in the review-matrix workspace binding. The source main at construction is `445026af54b83dcc58e8320b0dcb2e1eb4ba2094`, tree `8c4b109fa18838a642ea4514082387edb37698ee`. Focused acceptance passed 3/3; the full affected finalizer module passed 40 with 18 legacy-quarantined skips; the full matrix-resume module passed 18/18. Targeted Mypy, compilation, and diff checks passed. Hosted verification of the new PR head is pending.

The earlier incident remains explicit: `sentientos_data/vow/keys/salt.key` was deleted by mistaken cleanup, the original 32 bytes were not recovered, and no replacement key was generated. The new protection prevents future automated cleanup; it does not recover or rotate the key.

Post-merge main CI, Required Quality Gate, Docker, invariants, Codex CI, Docs Deploy, and Nightly Self Check succeeded for `445026af54b83dcc58e8320b0dcb2e1eb4ba2094`. Dependabot Graph Update failed on the invalid custom section header `[js]` in `requirements-extras.txt`; this will be addressed separately. A scheduled Federation Health execution for this exact main commit and the next scheduled Nightly Audit Integrity execution remain outstanding.

Latest verified main at construction: `445026af54b83dcc58e8320b0dcb2e1eb4ba2094`
Verified main tree: `8c4b109fa18838a642ea4514082387edb37698ee`
Latest construction segment: `work/construction/segments/0322-protect-vow-identity-from-finalizer-cleanup.md`
Sequence: 322
Latest segment SHA-256: `d139d1b0aff22e36d2f73559bed78f08a8a8a9f50ff164a3a920cfe4aac68686`

Next architectural dependency: independently attributable process-generation termination and no-inflight proof for resident transition recovery. The Federation Health changed-output fixture still requires an authorized Actions dispatch. Sequence 286 retains nine known and one unidentified unrecoverable payloads. The stale sequence-178 workspace remains untouched.
