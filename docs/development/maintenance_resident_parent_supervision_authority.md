# Maintenance Resident Parent Supervision Authority

`maintenance_resident_parent_supervision` is an implemented, bounded runtime contract.
The controller owns only the exact `sentientosd` launch contract derived from the
validated resident-runtime adoption configuration. The cooperative resident-adoption
path still owns live process-image replacement; parent supervision is the distinct,
narrow recovery path for an unexpectedly dead child.

The controller binds the executable, fixed `-m sentientosd` argv, working directory,
closed environment projection, resident configuration digest, and the exact canonical
maintenance generation reconstructed by successor custody. It never selects the newest
generation and never derives authority from process death. Before a launch or recovery,
it uses the resident transition-custody inspector and accepts only no-transition or
fully completed transition history. Incomplete, corrupt, contradictory, ambiguous,
foreign, or changed-lineage custody fails closed with durable evidence.

Each launch has digest-bound provenance. Process existence is not readiness: the child
remains maintenance-ineligible until the supplied canonical resident-readiness guard
accepts that exact launch provenance. Unexpected death causes a new custody and lineage
check, then at most a budgeted same-lineage replay. Restart history, exhaustion, panic,
explicit shutdown, current lineage, and launch evidence persist across controller
reconstruction. Lifecycle receipts are evidence and grant no authority.

`RuntimeSupervisor` and `ChildProcessServiceAdapter` remain generic lifecycle
primitives, not maintenance authority. Generic `real_service_restart` remains blocked.
This capability grants no arbitrary PID, executable, argv, environment, signal,
subprocess, service-manager, Git, network, provider, generation-selection, adoption,
or rollback authority.

The exact admitted goal is:

> Implement bounded parent supervision of an exact sentientosd child under resident transaction custody, permitting only exact maintenance-lineage process-death recovery, requiring exact resident launch provenance and post-restart resident readiness before maintenance effects resume.

Platform service installation, generic process management, automatic rollback, generic
service restart, parent self-update, and broader platform-specific supervision remain
deferred.
