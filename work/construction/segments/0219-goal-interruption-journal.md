# Sequence 219 — Journal interrupted goal tasks

Goal task outcomes were persisted only after an entire plan completed. A process exit between a task effect and final run persistence left no durable indication whether the task had started, and replaying the same plan could repeat its effect. The executor now records hash-chained task-start and terminal events, fsyncing each append. A fresh executor skips terminal tasks without replay and treats a start with no terminal record as an unknown outcome. It can continue other tasks in that plan.

Validation: 27 plan parsing/persistence, goal planning, execution, goal-state, and journal tests passed. Seven changed Python modules compiled and diff check passed. Fixture tests cover a simulated process interruption, no replay of an interrupted task, continuation of an independent task, exact terminal replay denial, and journal tampering/plan substitution rejection.

The journal preserves local custody and detects accidental or unsophisticated alteration through a digest chain; it is not an independently signed record.
