# Sequence 641 - constrain Windows custody child names

Sequence 641 closes a Windows custody namespace gap before replay-store publication work. Explicit child selections could name an NTFS alternate data stream, and case aliases could select the same file twice. Reads now reject stream/path syntax, invalid or oversized UTF-16 components, trailing-dot/space aliases, and case-folded duplicate selections. Directory traversal and enumerated child opens repeat the literal-name check.

PR #2746 candidate `0b3651186eea48446ac56aa3f99797a2ed92731e`, tree `868b3f1827e8c7f24e80c821b0035505221d38cc`, was based on main `ef7cf5a6441d4e920a518a2aed73019e43824dfb`. It merged normally as `78fbab1f935061da09e9e04c64ea93f019447946`, preserving the candidate tree and both parent identities. Native Git fetch independently confirmed the merge and tree.

The exact candidate passed 93 local focused, workflow, and composition tests; its local task acceptance verifier passed 23 required nodes. Targeted Mypy, Python syntax, workflow YAML, diff checks, and the prior 640-segment custody verifier passed. Branch Required Quality Gate #40056796534, full CI #40056796457, and Invariants #40056796563 passed. The hosted Administrator audit bound UID 0 and the candidate SHA/tree; strict audit and immutability passed, the pre-commit finalizer returned `ready_to_commit`, the post-commit finalizer returned `ready_for_pr_metadata`, and the metadata guard returned `pr_metadata_guard_ready`.

PR Quality Gate #40057023836, full CI #40057023852, Windows Custody #40057023846, Invariants #40057023865, Docker #40057023873, Lint #40057023913, Codex CI #40057023950, Release #40057023851, and Gradient #40057023833 passed. Native acceptance binds five exact passing nodes to the candidate, including a real NTFS alternate-stream fixture, ordinary successful reads, duplicate rejection, and both existing broad-write ACL cases.

Merged main passed Required Quality Gate #40057302340, full CI #40057302332, Windows Custody #40057302367, Invariants #40057302348, Docker #40057302326, Codex CI #40057302316, Docs Deploy #40057302333, and Nightly Self Check #40057302319. Forge Smoke #40057302374 was skipped by its workflow condition. Main Windows acceptance independently names the merge SHA and returns `task_acceptance_ready`.

GitHub artifact manifests and decoded upload logs agree on all recorded archive digests. The session network policy denied the returned artifact-download host, and API ZIP access was also unavailable. Independent ZIP-byte hash matches are not claimed. The evidence JSON preserves the exact advertised artifact IDs/digests and this limitation rather than treating upload metadata as independent byte custody.

The recovered starting checkout was clean but stale at sequence 638. No interrupted worktree was registered or present in the restored workspace. An isolated recovery verified all 21 changed blobs and modes, the complete non-truncated tree, and exact signed sequence-640 main commit; native Git history was subsequently refetched. Existing work was preserved.

This increment does not enable Windows replay publication, source composition, live peers, transport, local Health, admission, planning, execution, or decision authority. Next: inspect already provisioned private Windows replay histories through the existing handle reader, sharing canonical chain and signature verification while continuing to reject Windows writes.

Evidence: `work/construction/evidence/0641-constrain-windows-custody-child-namespace.json`.
