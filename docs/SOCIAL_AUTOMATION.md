# Social Automation Guidelines

SentientOS includes a lightweight browser automator for headless or
headful Chromium sessions.  The agent intentionally avoids proprietary platform
APIs and relies on Playwright-compatible drivers or the GUI controller as a
fallback.

## Configuration

- `social.enable`: master feature flag.
- `social.allow_interactive_web`: enable interactive flows; disable to force
  read-only capture.
- `social.domains_allowlist`: tuple of hostnames SentientOS is allowed to open.
- `social.daily_action_budget`: cap on automated actions every 24 hours.
- `social.require_quorum_for_social_post`: when `true` the council must approve
  before posting.
- `policy.autonomy_level`: `permissive` relaxes GUI and social safety gates.
- `policy.require_quorum_for_social_post`: global override layered on top of the
  social configuration.

## Metrics

- `sos_web_actions_total{kind=open|click|type|post}`
- `sos_social_posts_total`
- `sos_social_replies_total`
- `sos_observation_events_total{modality=screen}`

These counters are exported to `/admin/metrics` and mirrored as textfiles under
`glow/metrics/`.

## Operating the Automator

Use the CLI helpers for smoke tests and debugging:

- `make social-smoke URL="https://web.facebook.com"`
- `python sosctl.py social-smoke https://example.com --action click --selector ".like"`

The CLI automatically enables the module for the duration of the smoke test and
extends the allowlist with the provided URL.

For production runs wire social goals through the curiosity executor.  Council
quorum checks are enforced by default; the executor must log the intent and
capture the dry-run output before a post can be published.

## Storage Hygiene

Screen captures generated during social tasks are routed through
`memory_manager.store_observation` with the `screen` modality.  This ensures
textual summaries appear in daily digests while raw frames are kept only when a
highlight is explicitly marked as notable.
