# Sequence 461 — Correct pre-publication metadata-guard ordering

PR #2427 published the sequence-460 checkpoint candidate `524fd9c5a1b2279bc67a7b7e89428f92478430ed` at 2026-10-19 11:53:05 UTC. The push-triggered Required Quality Gate run #39247853406 began at 11:52:59 UTC but completed at 11:54:34 UTC. Its exact-candidate log shows `PR_TITLE` was empty in the push event, the finalizer fell back to the commit subject, and the metadata guard returned `pr_metadata_guard_ready` at 11:54:29 UTC. That result came after PR publication, so it does not satisfy the gate's pre-publication ordering.

PR #2427 was closed unmerged at 11:56:01 UTC. Its commit and evidence remain preserved in the sequence-461 candidate's ancestry; no tree or prior segment was rewritten. The verified main remains `cb1e60ac31e58ec411d431ee21cf530459066a61` / `00db0d978645244b5f3d241172b143b49c0e47a8`.

This record corrects the publication sequence: the replacement exact candidate must finish its push-triggered hosted finalizer and separate metadata guard before a new PR is opened. A post-publication QG rerun cannot retroactively satisfy that ordering. No source behavior, required gate, token scope, or protected workspace changed.
