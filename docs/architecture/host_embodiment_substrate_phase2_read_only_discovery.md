# Host Embodiment Substrate Phase 2: Read-Only Discovery

## Purpose

Phase 2 extends [Host Embodiment Substrate Phase 1](docs/architecture/host_embodiment_substrate_phase1.md) from supplied metadata to safe local body discovery. SentientOS can now collect read-only observations and feed them into the Capability Registry, Hardware/Sensor Inventory Manifest, and Host Resource Governor without changing the host.

The authority ladder remains:

`observe → model → propose → rehearse → authorize → fulfill → audit → rollback`

Phase 2 is only `observe → model → propose`.

## Safe observations collected

`sentientos/host_collectors.py` provides narrow collectors for:

- platform and architecture labels from the standard library;
- disk capacity/free space through `shutil.disk_usage` or an injected test provider;
- memory totals when safely available through standard-library OS metadata, otherwise unavailable/partial findings;
- CPU count and load averages where available, while leaving utilization unavailable when it cannot be computed safely;
- process count from numeric `/proc` entries when available, without reading command lines;
- local network interface names/link-address presence from read-only filesystem labels, without connectivity tests;
- service-manager platform labels, without service status mutation or restart;
- Linux thermal sensor values from injected or read-only `/sys/class/thermal` and `/sys/class/hwmon` readers;
- Linux fan RPM and PWM-signal presence from injected or read-only `/sys/class/hwmon` readers.

Every collector result records telemetry-only posture, warning/risk notes, privacy notes, and explicit false flags for host mutation, network use, and privileged action.

## Graceful degradation

Some platforms do not expose exact RAM, process, network, thermal, fan, PWM, or service-manager details through safe standard-library or read-only filesystem surfaces. Phase 2 records these as `partial`, `unavailable`, or `error` findings. It does not invent values and it does not call privileged tools such as `sensors-detect`, `pwmconfig`, or `fancontrol`.

## Thermal, fan, and PWM remain telemetry-only

Thermal zones and fan RPM are observations. PWM file presence is represented as `pwm_signal_observed=True`, `control_available=False`, `control_deferred=True`, `requires_future_allowlist=True`, and `requires_privilege_broker=True`.

PWM presence is not control authority. A visible `pwm*` file may indicate a possible controller surface, but Phase 2 does not prove hardware safety, operator policy, rollback behavior, panic handling, or privilege-broker admission. Therefore direct fan/PWM writes remain forbidden/deferred and direct thermal actuation remains forbidden/deferred.

## Integration flow

Collector results feed inventory through `build_host_inventory_from_collector_results(...)` and optional live collection through `collect_host_inventory_manifest(...)`. The manifest populates OS/platform, architecture, CPU, RAM, disk, network interface, thermal zone, fan/PWM, service-manager, warning, risk, and unsupported/deferred labels while preserving metadata-only validation.

Collector results feed resource pressure through `build_host_resource_telemetry_from_collector_results(...)` and optional evaluation through `evaluate_current_host_resource_pressure(...)`. The Host Resource Governor maps safe observations into telemetry snapshots and proposal-only pressure reports. Thermal pressure and fan-signal labels may produce inspection/future-policy candidates, but candidates do not execute and do not mutate the host.

Collector-backed inventory and resource reports can update the Capability Registry with observation/proposal-only status through `update_registry_from_host_inventory(...)` and `update_registry_from_host_resource_report(...)`. Direct fan/PWM/thermal control remains blocked.

## Future preparation

Phase 2 prepares future Privilege Broker and Actuation Fulfillment Layer work by making the local body visible before any action path exists. Future host control must still add policy, hardware allowlists, admission receipts, operator authorization, panic stop, audit receipts, rollback receipts, and tested fulfillment modules.

## Explicitly forbidden in Phase 2

Phase 2 must not perform:

- host mutation;
- direct fan/PWM writes;
- direct thermal actuation or cooling action;
- process killing;
- service restart;
- package installation;
- driver installation;
- network egress or connectivity tests;
- provider invocation;
- prompt assembly/export;
- federation transport, sync, adoption, merge, apply, install, execution, or remote execution;
- uncontrolled runtime authority expansion.


## Next phase

Phase 3 policy and proposal receipts are documented in `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md`; Phase 4 privilege broker eligibility is documented in `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`.
