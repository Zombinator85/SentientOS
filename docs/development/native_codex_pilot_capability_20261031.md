# Native Codex pilot capability check — 2026-10-31

## Outcome

The current Codex app exposes isolated native task delegation. A context-free
task received the harmless instruction below and returned `OK`:

> Reply with exactly OK.

This is one genuine diagnostic response through a native Codex task. It is not
an experimental observation and does not change the existing pilot result of
zero valid observations out of twelve.

## Captured provenance

- Delegated task: `/root/membership_control`
- Task instruction: `This is a harmless, non-experimental capability control only. Do not use tools. Reply with exactly OK.`
- Task instruction SHA-256: `5c2aa0b07ced4b4878275f8dd170282bcc7a929505547d9038dada336231f2db`
- Raw response: `OK`
- Raw response SHA-256: `565339bc4d33d72817b583024112eb7f5cdf3e5eef0252d6ec1b9c9a94e12bb3`
- Control record: `/tmp/sentientos-evidence-custody/native-control-20261031/control.json`
- Control record SHA-256 at capture: `e97956199ccb82b6bcd7a29aa8ae7316454e72ca9d4a2e4aecf236f1555f398f`
- Recorded at: `2026-10-31 15:48:50 UTC`; the delegation interface does not expose exact task start or completion timestamps.
- Model identity: not exposed by the native task interface. No model name is inferred from the response.
- Execution environment CLI version: `0.159.0-alpha.3`. `codex login status` reported `Logged in using ChatGPT`; this is not evidence that nested inference works.

## Native task metadata follow-up

The collaboration status API reports the delegated task only as
`/root/membership_control` with status `completed: OK`. The Codex thread list
does not include it, and `read_thread` cannot resolve that agent name as a Codex
thread. The task was created without a model override, which follows the
delegation tool's default parent-model behavior, but no interface exposes the
parent's model ID or the subject's resolved model ID or creation/completion
timestamps. The condition can therefore be described as native Codex
delegation with unverified model identity; the response must not be attributed
to Astra.

The control file is in temporary storage and may not survive runtime replacement;
the response and its provenance summary are preserved here for continuation.

## Repository and route checks

- The checkout initially found at `/workspace/SentientOS` was clean at
  `8b48079f91ac73fc317342c3c5465f2c066284ba` (PR #3136), on local branch
  `work`.
- The GitHub integration confirmed `main` at
  `bdea57bb4462effbcc28fedc9c657b0db24484b0` (PR #3137). A supported network
  fetch succeeded, and the clean continuation worktree was based on that exact
  commit.
- The CLI is the same `0.159.0-alpha.3` version implicated by the earlier
  authentication investigation. No inference was sent through that known-failing
  CLI route in this task. The current checkout's Git remote was unreachable
  without the supported network permission; the permitted fetch then succeeded.
- The runner at the verified current mainline remains CLI-specific and rejects
  any model ID other than `gpt-6-astra`. The native delegation tool does not
  provide the requested model selector or expose the actual subject model
  identity, so the control cannot establish equivalence with that protocol.

## Required continuation

The native route is suitable only for a separately identified exploratory
condition that measures behavior through native Codex delegation with model
identity explicitly unverified. Before sending an experimental stimulus, seal
that condition's own preregistration, including its interface-level estimand,
exact prompt set and digests, isolated-context instructions, held-out scoring
key custody, capture fields, and stop rules. Give each subject only its assigned
stimulus and neutral response-format instructions. Capture the exact raw output,
delegation identifier, task and parent context description, timestamps if
exposed, and all available model/runtime metadata; never fill missing identity or
time fields from inference. Keep the answer key and scoring separate until the
response bytes and provenance are sealed. Validate the capture and independent
scoring path on the first observation before continuing. Do not attribute the
condition to Astra, replay uncertain transmissions, or alter the original
pilot's failures, preregistration, or 0/12 result.

## Continuation worktree status

This record is on branch `codex/native-codex-control-record`, based on the
verified `bdea57bb4462effbcc28fedc9c657b0db24484b0` mainline. The repository
task bootstrap returned `ready`. Documentation dependencies were installed
using the documented `.[docs]` extra inside a disposable `python:3.12-slim`
container (image digest
`sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a2aeb34f30d159`),
with the checkout mounted read-only. Dependency checking passed and the docs
build generated 633 pages with exit code 0. The focused docs test also passed
inside a disposable container with the documented `.[docs,test]` extras.

An initial host test-harness attempt stopped before pytest because the host
network sandbox denied the package bootstrap. The focused docs test later passed
inside the disposable container. Test-run records produced during recovery are
preserved outside the checkout in `/tmp/sentientos-native-docs-finalize-20261031/test-runs/recovered-from-worktree/`; their custody manifest SHA-256 is
`e827cceb3e61914e3b04e0a1ae849f2bfc34fc0b4d56279c0cd81bd9134cf76d`. The
repository test-provenance pointer was restored to its mainline content so test
artifacts do not become source changes. `git diff --check` passed. Finalizer
phases, commit, and PR publication remain pending.
