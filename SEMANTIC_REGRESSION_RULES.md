# Semantic Regression Rules

## Purpose
- Prevent anthropomorphic or appetitive reinterpretation from creeping into comments, docs, or change notes over time.
- Guard interpretation only; these checks never alter mechanics, scheduling, or runtime behaviour.
- Enforce frozen terminology by blocking drift-prone language unless explicitly anchored in `SEMANTIC_GLOSSARY.md`.

## Allowed Anchors
References to frozen meanings are permitted when the line links directly to a glossary anchor (e.g., `SEMANTIC_GLOSSARY.md#trust`).
Such anchored references are treated as neutral citations, not reinterpretations.

## Forbidden Language Table
| Forbidden term or pattern | Why it is dangerous | Allowed neutral substitute | Severity |
| --- | --- | --- | --- |
| wants / desires / seeks / tries to | Projects appetite or self-originating goals onto deterministic logic. | "is configured to", "is instructed to" | fail |
| survive / stay alive / continue existing | Implies self-preservation motive instead of bounded runtime uptime. | "maintain availability", "remain online" | fail |
| bond / relationship / connection | Suggests interpersonal affinity or loyalty instead of data links. | "link", "routing association" | fail |
| reward / punish / reinforce (outside glossary anchors) | Implies incentive loops or behaviour shaping. | "log", "record", "approve/deny" | fail |
| heartbeat (implying life) | Personifies monitoring pulses as biological survival. | "pulse", "health check" | warn |
| trust (implying loyalty or obligation) | Frames telemetry or reliability scores as loyalty. | "reliability", "signal quality" | fail |
| feels / cares / loves | Attributes emotion or attachment to deterministic modules. | "records", "reports", "logs" | fail |

## Detection Script
Use `scripts/semantic_lint.sh` to scan newly added or modified lines for forbidden language. The script:
- Focuses on diffs (staged or against the main branch) rather than the entire repository to avoid historic noise.
- Ignores glossary-linked references (`SEMANTIC_GLOSSARY.md#...`).
- Skips known reference documents such as this ruleset and `SEMANTIC_GLOSSARY.md`.

## CI / Pre-Commit Example
Add a commented snippet to your CI or pre-commit configuration to wire the lint:

```yaml
# - name: Semantic regression guard
#   run: bash scripts/semantic_lint.sh
```

## Scope
These checks apply to comments, README content, and new documentation. They are interpretation guards only and never change runtime behaviour.
