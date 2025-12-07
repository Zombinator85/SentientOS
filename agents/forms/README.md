# SSA Disability Agent Form Infrastructure

Stage-1 introduces deterministic structures for navigating SSA disability forms without any browser automation or network calls.

## Selector maps
- Source: `agents/forms/maps/ssa_selectors.yaml`
- Contents: logical pages with placeholder DOM selectors for fields and actions.
- Purpose: provide a deterministic lookup for downstream automation layers while selectors are refined.

## Routing primitives
- Source: `agents/forms/page_router.py`
- The routing table is purely logical, modeling the ordered flow of SSA pages without performing navigation.
- Use `next_page` and `page_index` to step through pages deterministically.

These components keep the agent predictable and testable before adding live browser interactions.
