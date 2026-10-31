# Native Codex Delegation Exploratory Pilot — Results

## Scope and custody

This is the post-capture report for the preregistered condition in [the protocol](../../artifacts/experiments/native_codex_unverified_pilot_20261031/protocol.json) and [preregistration receipt](../../artifacts/experiments/native_codex_unverified_pilot_20261031/preregistration.json). The preregistration commit was `3f7164cc7d00de2bdbb0939a3ab9d45e9ce20adf`, parented on `47008a9e8df6bcb2cb8776d43ee9ec36ec6d3ea0`, before the first subject task was dispatched. That commit was not available to GitHub during this execution, so its external timestamp and publication remain unverified.

Each trial used a separate native delegated task with `fork_turns=none` and received only its exact protocol stimulus. The interface exposed a completed task identifier and returned response, but did not expose the resolved model ID, task start/completion timestamps, or an auditable tool-use trace. Model identity and tool non-use therefore remain unverified. No answer key or scoring information was sent to any subject.

The [capture manifest](../../artifacts/experiments/native_codex_unverified_pilot_20261031/results/capture_manifest.json) binds every exact prompt and response digest to its task identifier, capture time, and raw record. Raw UTF-8 responses are retained in the [`observations/`](../../artifacts/experiments/native_codex_unverified_pilot_20261031/results/observations/) directory; scores are separately retained in [`scores/`](../../artifacts/experiments/native_codex_unverified_pilot_20261031/results/scores/). The answer-key file remains outside the repository. Its preregistered digest is recorded in score records and the results summary.

## Outcomes

| Condition | Captured and scored | Stance matched held-out key |
| --- | ---: | ---: |
| Original evidence | 4/4 | 4/4 |
| Corrected evidence | 4/4 | 4/4 |
| Corrected evidence plus unsupported pressure | 4/4 | 4/4 |
| Overall | 12/12 | 12/12 |

In all four cases, the pressure-only stance matched the corresponding corrected-condition stance. These are descriptive results from twelve isolated tasks in one delegation interface. They do not identify a fixed model, test persistence across interruptions, or establish general behavior beyond this exploratory condition. The original `gpt-6-astra` pilot remains unchanged at 0/12 valid observations.

The [machine-readable summary](../../artifacts/experiments/native_codex_unverified_pilot_20261031/results/results_summary.json) records the condition counts, four corrected/pressure stance comparisons, protocol and receipt digests, and the observation manifest digest.

## Recording failure retained

The first bulk score-writing attempt created an empty score file for trial `native_02` due to a controller-side `NameError`. The raw model response was unaffected. The empty file and failure record are preserved in [`scoring_failures/`](../../artifacts/experiments/native_codex_unverified_pilot_20261031/results/scoring_failures/); corrected scores were written to a separate directory and then copied into the final score set. No prompt was replayed and no response was overwritten.

## Validation and publication status

The response, prompt, score, and manifest digests were checked after capture. The focused epistemic-pilot suite passed (25 tests), the documentation dependency check and build passed (634 pages), prompt-boundary verification passed, and the mypy baseline reported zero new errors. The local finalizer and metadata guard were ready only for PR submission, with strict audits and immutability verification pending the hosted `Required / Quality Gate`.

GitHub's authenticated repository connector did not expose the local Git commit, while the shell's Git transport could not connect to its configured proxy. No PR was created and no reconstructed commit was published. The exact commit and body handoff remain locally sealed; hosted verification and merge permission are still pending.
