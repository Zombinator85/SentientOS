# WAN Fault Models

The WAN federation wing injects deterministic and bounded cross-host faults.

## Scenarios

- `wan_partition_recovery`
  - isolates one host
  - heals partition
  - validates bounded recovery
- `wan_asymmetric_loss`
  - asymmetric loss for one host/fault domain
  - validates degraded isolation behavior
- `wan_epoch_rotation_under_partition`
  - rotates trust epoch on partitioned host
  - heals and verifies propagation compatibility

## Determinism and bounds

- Schedule is seeded and topology-aware.
- Timeline is emitted in `fault_timeline.json` and `wan_faults.jsonl`.
- Runtime remains bounded by scenario duration and `--runtime-s`.
