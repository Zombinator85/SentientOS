# Pulse Key Epochs

Pulse signatures are bound to `pulse_epoch_id` and validated against epoch state. Retired epochs are rejected by default and only accepted inside an explicitly configured replay window (`SENTIENTOS_PULSE_RETIRED_REPLAY_SECONDS`).

## Operator commands
- `make pulse-key-status`
- `make pulse-key-rotate DRY_RUN=1`
- `python -m scripts.rotate_pulse_keys --dry-run`
