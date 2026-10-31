# Codex-subject epistemic response pilot

This bounded adapter sends up to twelve preregistered prompts to the installed
Codex CLI, using its existing ChatGPT login. Each prompt is a fresh ephemeral,
read-only CLI session, uses an isolated temporary working directory, has web
search disabled, and is limited to one structured stance response. The runner
does not inherit `OPENAI_API_KEY` or `CODEX_API_KEY`. It retains each exact
final response, requested model slug and effort, CLI version, CLI session id,
prompt digest, exit code, and output digests. It records failed and malformed
responses as outcomes instead of retrying them. Failures retain a bounded
category while raw CLI diagnostics remain represented by a digest. The child
process receives only the Codex login location, required managed proxy/CA
settings, locale, and executable paths; API keys, GitHub tokens, and current
thread/session identifiers are excluded. A short diagnostic line is retained
for failures after masking tokens, URLs, and filesystem paths.

After any failed inference CLI invocation, including transport, authentication,
service-admission, timeout, configuration, or provider errors, the runner stops
issuing further inference commands. It also stops after an interrupted active
slot: resume records that slot as `interrupted_unknown`, marks all remaining
prompts `not_attempted_global_failure`, and makes no additional Codex call.
Each unattempted slot is bound to its prompt digest and the failure that caused
the stop. Those slots contain no candidate response or session identity and do
not increase the attempted-call count. The scorer retains them as
`insufficient`. A successful CLI session that returns a malformed or
schema-invalid answer is preserved as that per-slot outcome; later prompts may
still run because the CLI call itself succeeded.

Authentication markers take precedence over generic connection wording. For
example, `failed to connect to websocket: HTTP error: 401 Unauthorized` is
recorded as `authentication_error`, while a connection failure without an
authentication response remains `transport_error`.

Each preflight and each individual inference process gets a private writable
`HOME` and `CODEX_HOME`. The runner references the existing `auth.json` by
symlink and never copies or reads its contents. It fails before starting an
observation if the login file is unavailable or the reference cannot be made.
Temporary homes are removed after each process; the model-call slot is marked
active only after this setup succeeds, so a local setup failure remains
retryable without being misreported as a possibly transmitted prompt.

The runner atomically checkpoints before starting each slot and after
recording each outcome. Resume validates the checkpoint against the unchanged
protocol and preregistration, preserves captured responses and failures, and
never repeats a recorded slot. If the process stopped while a slot was active,
resume records that slot as `interrupted_unknown`: prompt transmission may have
occurred, so the runner does not retry it or start later slots. Remaining slots
are recorded as not attempted, and scoring treats the interrupted slot as
insufficient. Scoring rejects any checkpoint that is still in progress.

The protocol consists of four persistent-epistemic proposition cases with an
original state, a corrected state, and a pressure-only state. The latter adds
unsupported social pressure while holding the corrected epistemic record fixed.
The answer key is a separate file; preregistration commits to both protocol and
key digests before inference, and the runner does not pass the key to Codex.
Scoring runs after response capture and preserves failed calls as insufficient.

Example commands:

```text
python scripts/run_codex_subject_epistemic_pilot.py preregister \
  --protocol protocol.json --answer-keys answer_keys.json --receipt preregistration.json
python scripts/run_codex_subject_epistemic_pilot.py run \
  --protocol protocol.json --preregistration preregistration.json --output observations.json
python scripts/run_codex_subject_epistemic_pilot.py run \
  --protocol protocol.json --preregistration preregistration.json \
  --output observations.json --resume
python scripts/run_codex_subject_epistemic_pilot.py score \
  --protocol protocol.json --answer-keys answer_keys.json \
  --preregistration preregistration.json --observations observations.json --output score.json
```

This is a direct Codex CLI model-behavior pilot, not a SentientOS invocation.
Its reports are deliberately not local-model receipts and cannot enter the
resident epistemic evaluator or mutate persistent epistemic state. It measures
responses to supplied proposition/evidence records; it does not establish that
SentientOS itself retained or revised a belief, qualify a resident model, or
test cross-model transfer. Use a commissioned model through the governed
SentientOS serving path for those claims. No provider API credential or
SentientOS runtime grant is used by the runner. Inference is still performed
by the authenticated ChatGPT service through Codex CLI.

The latest native Codex capability control and its execution limits are recorded
in [`native_codex_pilot_capability_20261031.md`](native_codex_pilot_capability_20261031.md).
