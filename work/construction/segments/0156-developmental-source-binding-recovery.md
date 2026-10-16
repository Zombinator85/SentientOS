# Sequence 156 — Reject ambiguous recovered source bindings

**Source:** `a2959caa57010fe982079035150b98245ff54563`  
**Tree:** `7f700556bfe2e6be204dfb448bc97c8492f78673`

Recovery already verifies candidate and record digests, exact source rows, admission linkage, and deterministic receipts. Inspection found the payload-bearing candidate form built a `source_id` dictionary without rejecting duplicate IDs or extra unreferenced source rows. Added one owner-level binding check to append and recovery: each retained fact's source row must exactly match one unique selected source, all selected source rows must be referenced, and source digests must be canonical. Historical records that omit selected fact payloads remain compatible.

The focused positive restart and adversarial recomputed-identity duplicate-source recovery cases passed (**2 passed**); both changed Python files compiled. This is hermetic custody testing only. No model was invoked and no acquisition, transfer, improvement, or production behavior is established.

Next: complete a task-relevant acquisition example using an existing independently scored task outcome as the source, while keeping the scoring oracle out of cognition context and testing history present/withheld/restored through the ordinary admission path.
