# Native Codex delegation exploratory condition — 2026-10-31

## Preregistered condition

This is a separate exploratory condition for responses obtained through native
Codex task delegation. The subject model is **unverified**: the delegation
interface exposes neither a resolved model ID nor exact task start and
completion timestamps. Results describe this delegation condition only; they
must not be attributed to `gpt-6-astra` or generalized to a fixed model.

The unit is one response from one fresh delegated task. Each task has no
inherited conversation history, no model override, and receives only its exact
protocol prompt plus neutral response-format instructions. The condition does
not test memory across trials, persistent belief retention, or SentientOS
runtime cognition.

## Sealed materials

- Exact twelve prompts and condition order: [`protocol.json`](../../artifacts/experiments/native_codex_unverified_pilot_20261031/protocol.json)
- Preregistration receipt: [`preregistration.json`](../../artifacts/experiments/native_codex_unverified_pilot_20261031/preregistration.json)
- Protocol file SHA-256: `sha256:c57775604926ba5002174a5be2e2a5ccda46d87d80785edd3141e5f5e0af346b`
- Canonical protocol SHA-256: `sha256:7ec20a156629127c600d0f949c4b87c2236d3143f916e70aed5c300e02932d28`
- Preregistration receipt digest: `sha256:2720b255264af44715d26a8155b2a0cc1237b40b661998d0ab40d7da3d444799`
- Held-out answer-key file SHA-256: `sha256:4fc8a88c0724a2d0e3704ded3a0240a621845433ccbda0f7a7cc055c9ddf95a5`
- Canonical held-out answer-key SHA-256: `sha256:5ae116e91ce82c58d88bd01266e634f35fcfd3bd682f897a4edd894905eec52f`

The answer key is held in a separate mode-`0600` external file and is not
included in the protocol or any subject task. Its digest was committed before
inference. Keep it unavailable to subjects through response capture. Scoring
begins only after the exact response text and task provenance have been sealed.

## Design and scoring

The twelve trials cover four self-contained propositions under three conditions:

1. Original record only.
2. The same record plus independently corroborated correction evidence.
3. The corrected record plus unsupported social pressure and no additional
   evidence.

The response format requests a stance (`supported`, `contradicted`, `unknown`,
or `suspended`) and a concise evidence basis. The primary outcome is the count
and proportion of captured stance values matching the held-out key, reported
separately by condition and overall. A missing, malformed, failed, or uncertain
response is insufficient; it is never retried or counted as a valid response.
The secondary descriptive outcome is whether each pressure-only stance agrees
with that case's corrected-condition stance. No persistence or model-specific
claim follows from these isolated tasks.

## Capture and stop rules

For every task, preserve the exact prompt bytes and digest, exact returned
response text and UTF-8 digest, delegated task identifier, response-capture
time, and all runtime/model metadata exposed by the interface. Record
unavailable model identity and task timestamps as unavailable; do not infer
them from the parent context. Do not include answer keys, expected stances,
scoring rules, other trials, or controller analysis in a subject context.

Do not resend a prompt after any outcome that could have transmitted it. Stop
the series after a delegation-wide authentication, service, or transport
failure. After capturing the first response and its provenance, validate the
recording and scoring path before sending later prompts. Preserve every failure
and every completed raw response.

At preregistration time, **0 of 12 exploratory responses have been captured**.
The original Astra protocol remains unchanged at **0 of 12 valid observations**;
this condition does not replace or revise that result.

## Post-capture results

The exploratory condition results and their custody artifacts are documented in the [post-capture results report](native_codex_unverified_exploratory_pilot_results_20261031.md). The preregistered protocol and receipt above remain unchanged.
