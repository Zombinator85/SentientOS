# Maintenance resident-runtime adoption

The closed `sentientos.maintenance_resident_runtime_adoption_config:v1` binds the
continuity and successor configurations, repository identity, exact interpreter,
`sentientosd` module/entrypoint/cwd, a bounded environment policy, external custody
paths, STOP marker, time bounds, and transition bound. The daemon selects it only
through `SENTIENTOS_MAINTENANCE_RESIDENT_RUNTIME_ADOPTION_CONFIG`.

The implemented order is: N resident and wake; canonical maintenance closure;
repository advancement; automatic N+1 continuity; successor configuration;
predecessor wake quiescence; successor wake withholding; exact `python -m
sentientosd` POSIX `execve`; N+1 launch-provenance and readiness custody; N+1 wake;
then automatic continuity resumes. Repository state, authority/config generation,
and the resident process generation are distinct and are never inferred from one
another.

Baseline startup records immutable launch provenance before later repository
advancement. A separate digest-chained journal records intent, predecessor proof,
runtime quiescence, exec request, successor provenance, readiness, and completion.
STOP or maintenance pause prevents a new transition. Unsupported platforms and
exec failure remain quiescent and fail closed; there is no rollback. Recovery may
only finish the exact durable transition whose marker and bytes agree.

This capability supplies no command runner, arbitrary argv/environment, Git
mutation, process killer, parent supervisor, Windows service behavior, generic
service restart, network/provider authority, authority widening, or expiry change.
