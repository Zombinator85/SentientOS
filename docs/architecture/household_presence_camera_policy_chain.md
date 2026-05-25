# Household Presence Camera Policy Chain

Metadata-only offline chain composing event bridge, zone resolver, deadzone redaction, and redaction pipeline.
No media processing, no live adapters, and no camera/runtime authority.

Stages: input_loaded, event_bridge_normalized, zone_resolved, redaction_contract_evaluated, downstream_route_selected, operator_review_marked, blocked.

Routes include live/security/wildlife/nuisance/protected-care outputs plus policy block routes.
