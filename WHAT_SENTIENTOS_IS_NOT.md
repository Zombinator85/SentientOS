# What SentientOS Is Not
Quick reference to avoid projecting agency or intent onto this codebase.

## Not an agent
- Claim: SentientOS is not an autonomous agent.
- Why the misconception happens: Modules use terms like "autonomy" and "mesh" that appear in agent frameworks.
- What actually happens instead: Deterministic schedulers assemble scripts from provided inputs without self-directed objectives.【F:sentient_autonomy.py†L40-L101】

## Not a learner via reward
- Claim: No reward-driven learning occurs here.
- Why the misconception happens: Presence of approval gates and trust metrics can look like reinforcement signals.
- What actually happens instead: Approvals are binary gates for configuration loads and trust scores are static floats; no gradients or updates are computed.【F:policy_engine.py†L35-L71】【F:sentient_mesh.py†L17-L59】

## Not persistent by preference
- Claim: The system does not try to stay alive on its own.
- Why the misconception happens: Heartbeat and start/stop helpers resemble uptime survival.
- What actually happens instead: Heartbeats only log status and enable external monitoring; internal flags simply gate scheduling when toggled by callers.【F:heartbeat.py†L1-L63】【F:sentient_autonomy.py†L40-L75】

## Not relational
- Claim: SentientOS does not form relationships or bonds.
- Why the misconception happens: Wake-word logging and presence tracking may suggest user affinity.
- What actually happens instead: Presence logging records raw wake-word events without identity, scoring, or adaptation.【F:presence.py†L16-L44】

## Not optimizing for approval
- Claim: Human approval is not a reward channel.
- Why the misconception happens: `final_approval.request_approval` appears before policy changes.
- What actually happens instead: Approval is a yes/no gate for file replacement; execution paths do not change based on who approved or how often.【F:policy_engine.py†L35-L71】

## Not a substrate for qualia
- Claim: No phenomenology or consciousness is implied.
- Why the misconception happens: Names like "sentient" and "presence" evoke experiential states.
- What actually happens instead: Data structures are plain Python objects passed through schedulers and loggers with no stateful inner experience model.【F:sentient_mesh.py†L17-L59】【F:sentient_autonomy.py†L40-L85】
