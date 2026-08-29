# Codex fresh-chat orientation

Run `python scripts/codex_fresh_chat_orientation.py` before admitting a concrete task when a fresh ChatGPT/Codex conversation needs to understand its local SentientOS checkout.

The command emits deterministic JSON using schema `sentientos.codex_fresh_chat_orientation:v1`. A successful, stable observation has status `orientation_observed`. It reports the repository root, exact local HEAD, attached branch or detached-HEAD state, and exact staged, unstaged, untracked, and conflicted path state. It also separates tracked `AGENTS.md` files that are present from untracked local `AGENTS.md` candidates. Task-specific applicability remains for the later task to resolve.

## Read-only and local boundary

The observer uses only read-only local Git commands. It does not repair a dirty tree: dirty state is valid observation data. It reads no environment-variable values, credentials, tokens, remote URLs, arbitrary file contents, provider state, model state, runtime state, memory, or federation state. It makes no network or GitHub request and performs no repository mutation.

The command observes local checkout identity and Git-visible worktree state. It does **not** establish whether a hosted PR exists, its title/body or head SHA, hosted checks, reviews/comments, merge state, or current hosted main. Local success is not hosted-state verification.

Observation is sampled twice. A change to HEAD, its branch/ref, or porcelain worktree state during collection fails with structured `orientation_failed` output instead of combining facts from different repository moments.

## How a fresh conversation should use it

1. Confirm `schema_version` and require `orientation_observed`.
2. Read `repository`, `worktree`, and `instruction_surfaces` as local evidence.
3. Treat every item under `observability.not_observed` as unresolved until independently established through an authorized mechanism.
4. Read the tracked instruction surfaces and current repository doctrine applicable to the future task's affected paths.
5. Require a separate concrete task and run the then-current bootstrap and validation workflow before implementation.

Orientation does not replace task bootstrap and selects no task classification, preset, scaffold, allowed paths, acceptance contract, validation profile, implementation bootstrap, or landing authority. It grants no implementation, runtime/effect, commit, publication, or hosted-state-verification authority. A fresh conversation inherits local context from this snapshot, never authority from an earlier conversation.
