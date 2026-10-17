# Active construction checkpoint

Sequence 321 records cross-process transition request exclusion, local focused verification, and an identity-key cleanup incident. Current main is `d8a692cb646950df9a4bf64e84dd92c26042fc62`, tree `b152d3f309a28f27c6d398acd991592f0ce8ed70`. The tested tree is identical, source commit `08179763200d24c406da2bebb6b5e1ea52f0c65e`. The implementation serializes request admission and receipt across daemon processes without claiming process-death recovery or permitting replay.

Sequence 320 records GitHub scheduled Federation Health run 39028288072 on historical main commit `f0564c9f780e1f86a53e84348ec4a4a9534c0e48`, tree `62d9b93b038f92a5df1b25d6cb7cc70847a86f23`. The current main source independently reacquired for this increment is `5f011dc9d14fa872deb0320bb2ed9476c3a9f414`, tree `ffe7dd1edd4873d80ea5af8076b607b6b328d272`. Hosted Administrator preflight and generation passed; the independently downloaded artifact matched GitHub SHA-256 and reported one node, zero recent events, quiet. The least-privilege publisher succeeded and correctly made no PR because output was unchanged. The labeled changed-output fixture remains unexecuted because this session lacks a workflow-dispatch operation and a valid shell GH_TOKEN.

Latest verified main at construction: `d8a692cb646950df9a4bf64e84dd92c26042fc62`
Verified current-main tree: `b152d3f309a28f27c6d398acd991592f0ce8ed70`
Latest construction segment: `work/construction/segments/0321-serialize-resident-transition-operator-across-processes.md`
Sequence: 321
Latest segment SHA-256: `e94062aaed6f4d4774ebb664e5c07419ce7819cccd89f47072402f27a5839fab`

Identity incident: the exact 32-byte default PII hashing salt at `sentientos_data/vow/keys/salt.key` was deleted by a mistaken finalizer cleanup classification and remains unrecovered; no replacement was generated.

Next architectural dependency: independently attributable process-generation termination and no-inflight evidence for resident transition recovery, preserving fail-closed restart and no stage replay. Production A→B→A still requires exact commissioned identities, receipts, setup, and operator approval. Sequence 286 still has nine known and one unidentified unrecoverable payloads. The stale sequence-178 workspace remains untouched.
