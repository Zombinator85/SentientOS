# Initial resident genesis provisioning

This operator-facing composer is the missing fresh-install bridge:

```text
operator provisioning manifest
-> activation profile bundle
-> maintenance/watchdog configuration
-> health/collector/autonomy configuration
-> wake configuration
-> wake adoption
-> commissioning manifest
-> commissioning doctor READY
--------------------------------
later operator approval
--------------------------------
generation-zero commissioning
```

The closed `sentientos.maintenance_initial_resident_genesis_provisioning_manifest:v1`
requires an explicit stable repository identity, exact checkout SHA, and an existing
operator-selected local ref. Identity is not inferred from a remote. In
`local_fast_forward_base_ref` mode no remote, `origin`, or `main` branch is required;
the selected base and tracked refs must be identical and resolve to the exact SHA.

The composer delegates profile rendering and all component validation to their
existing canonical implementations. It writes only immutable external configuration
metadata, permits exact replay, and rejects conflicting bytes, symlinks, repository-
internal custody, identity drift, SHA drift, ref drift, and digest tampering.

Profile rendering is not a runtime authority grant. Wake-adoption rendering is not
adoption execution. Provisioning is not commissioning. The provisioner never runs a
probe, collector, autonomy cycle, wake cycle, watchdog, Codex, or resident; it never
mutates Git or creates generation zero. Only the later commissioner may create
generation zero, after a separate external operator approval and control-plane
admission.

The CLI supports `write-template`, `doctor`, `render`, `verify`, `inspect`, and
`print-commissioning-inputs`. All except `render` are read-only. The final command
returns exact paths and digests needed by the later commissioning workflow without
ambient newest-file discovery.
