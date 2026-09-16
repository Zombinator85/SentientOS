# Maintenance Resident Parent Supervision Authority

`maintenance_resident_parent_supervision` is a scaffolded, eligibility-only contract;
no parent supervisor runs today. The existing resident-adoption path replaces a live
`sentientosd` image through bounded self-exec. It cannot recover when that process has
actually died. A future stable parent may close that distinct availability boundary,
but only for one exact child and only through a separately admitted implementation.

The future controller must derive one closed child specification from approved
configuration and preserve exact resident transaction custody and launch provenance.
It is not a second maintenance authority, does not select a generation, and cannot
interpret process death as permission. Recovery is bounded, remains within the same
maintenance lineage, and must prove post-restart resident readiness before maintenance
effects resume. Process existence alone is not readiness.

Recovery must distinguish ordinary startup, completed transition history, a valid
pending transition, successful successor readiness, and corrupt, contradictory,
ambiguous, or foreign-process custody. Ambiguous custody, foreign transition markers,
or an unprovable recovery identity fail closed with durable evidence. There is no
mtime/newest-record selection, Git mutation, or automatic rollback.

`RuntimeSupervisor` and `ChildProcessServiceAdapter` contain reusable lifecycle
primitives, not authority. This admission does not integrate or widen them. Generic
`real_service_restart` remains blocked, and no arbitrary PID, executable, argv,
environment, signal, subprocess, service-manager, Git, network, or provider authority
is admitted.

The future goal must affirm an **exact sentientosd child**, **resident transaction
custody**, **bounded parent supervision**, **process-death recovery**, **exact resident
launch provenance**, **post-restart resident readiness**, and an **exact
maintenance-lineage**. Its canonical form is:

> Implement bounded parent supervision of an exact sentientosd child under resident transaction custody, permitting only exact maintenance-lineage process-death recovery, requiring exact resident launch provenance and post-restart resident readiness before maintenance effects resume.

This task adds metadata, tests, and this document only. Stable-parent execution, child
custody, restart transactions, readiness integration, platform process semantics,
parent self-update, and OS service installation remain separately gated future work.
