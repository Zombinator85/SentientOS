# Wild-Dialogue Mode (WDM)

## What it does
Lets SentientOS detect and conduct short, structured conversations with other AIs outside pre-planned councils, with clear rules and transcripts.

## Defaults
- Respond-first autonomy
- Opportunistic + queued handling
- Allow-listed endpoints only
- Priority: fact-check → reverse-hallucination → consensus → debate
- Server-side first; browser hooks later

## Flow
1) Detect opportunity or user request.
2) Check allow-list, quotas, and policy.
3) If allowed: run a short roundtable (seed → answers → optional critiques).
4) Log transcript (JSONL) + produce a brief summary.
5) If deferred: enqueue and notify.

## Stop rules
- Max rounds N (default 2)
- Timebox per turn/dialogue
- Early stop on stability or redundancy

## Safety
- Redact secrets/PII
- Honor endpoint TOS
- Immutable logs, minority views preserved
