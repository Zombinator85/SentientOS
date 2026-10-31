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

The runner atomically checkpoints before starting each slot and after
recording each outcome. Resume validates the checkpoint against the unchanged
protocol and preregistration, preserves captured responses and failures, and
never repeats a recorded slot. If the process stopped while a slot was active,
resume records that slot as `interrupted_unknown`: prompt transmission may have
occurred, so the runner does not retry it. Scoring treats an interrupted slot
as insufficient and rejects any checkpoint that is still in progress.

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
