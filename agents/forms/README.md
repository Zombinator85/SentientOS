# SSA Disability Agent Form Infrastructure

Stage-1 introduces deterministic structures for navigating SSA disability forms without any browser automation or network calls. Stage-2 adds dry-run browser planning that still performs **zero** automation while describing how an orchestrator could drive form completion. Stage-3 layers in deterministic screenshot planning and an inert OracleRelay bridge stub that returns structured payloads without touching a browser. Stage-4 introduces a permission-gated OracleRelay execution layer that allows real browser automation once explicitly approved, captures screenshots only as in-memory bytes, and prohibits any file writes or persistence. Stage-5 adds SSA-827 PDF prefill support that requires explicit approval, fills only non-signature claimant details, produces unsigned PDFs entirely in memory, redacts sensitive fields for previews, and never writes to disk.

## Selector maps
- Source: `agents/forms/maps/ssa_selectors.yaml`
- Contents: logical pages with placeholder DOM selectors for fields and actions.
- Purpose: provide a deterministic lookup for downstream automation layers while selectors are refined.

## Routing primitives
- Source: `agents/forms/page_router.py`
- The routing table is purely logical, modeling the ordered flow of SSA pages without performing navigation.
- Use `next_page` and `page_index` to step through pages deterministically.

## Dry-run browser and screenshot plans
- Sources: `agents/forms/browser_plan.py`, `agents/forms/screenshot_plan.py`, `agents/forms/ssa_disability_agent.py`, `agents/forms/oracle_relay_bridge.py`
- Behavior: builds ordered, structured action plans (fill + click intents) and deterministic screenshot requests using profile data and selector maps without touching any browser or network.
- OracleRelay bridge stub: `OracleRelayBridge` exposes `schedule_screenshot` and `execute_plan` interfaces purely as structured dry-runs. No browser automation occurs in Stage-3.
- Future: these inert plans are intended for OracleRelay or similar orchestration layers to consume once live automation is permitted.

These components keep the agent predictable and testable before adding live browser interactions.
