# Sequence 268 - Wire current serving identity into canonical planning

Extended the orchestrator with optional prior-projection and target-identity-observer inputs. It reads the observer's existing `observed_current_model_identity` exactly once before allocation, derives the same canonical identity digest used by developmental evidence, timestamps it at planning, and passes the exact observation through bounded allocation and plan creation. Allocation artifacts and plan context retain the digest and timestamp. No current session is acquired, no model is loaded or invoked, and the existing default path remains inert.

Validation: 13 selected orchestrator allocation, plan creation, applicability, and executor tests passed; compilation and AST parsing passed. The fake serving observer confirms a single read-only observation and rejects session acquisition or invocation.

Limits: the daemon does not yet configure these optional inputs, and a verified prior projection still must be supplied by its owning composition layer. Target identity use remains fail-closed when absent. No live inference, production effect, or authority expansion is claimed.
