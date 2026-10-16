# Sequence 218 — Record unsupported planning omissions

The goal planner emitted `fetch` and `doc_update` rows despite having no matching executors. Those rows made ordinary plans partial and obscured which work was genuinely planned. The planner now excludes unsupported operations from executable tasks and stores explicit per-goal omission records with `task_kind_not_implemented`. Version-1 plans without an omissions field remain readable; new plans validate omission identity and preserve it through serialization.

Validation: 23 goal planning, execution, state, and work-plan persistence tests passed. Four changed Python modules compiled and diff check passed. No fetching or documentation mutation capability was added.
