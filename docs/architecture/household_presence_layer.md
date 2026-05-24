# Household Presence Layer

Metadata-only doctrine/model layer for household embodiment. This subsystem defines deterministic policy taxonomy and discernment rules without any live sensor access.

## Core doctrine
SentientOS is a household presence system, not a surveillance appliance.

## Scope
- Metadata-only policy taxonomy across zones, modalities, memory classes, and entities.
- Deterministic JSON artifact generation and validation.
- No camera/microphone/Wi-Fi/RF/Quest/network/provider/subprocess/action-wing execution.

## CLI
`python scripts/build_household_presence_layer.py build-default --output <path>`
`python scripts/build_household_presence_layer.py validate --input <path>`
`python scripts/build_household_presence_layer.py summarize --input <path>`

## Future adapter sequence
1. hardware inventory / sensory device discovery
2. exterior camera event bridge
3. camera privacy/deadzone mask
4. wildlife ledger adapter
5. roomfield/Wi-Fi RF stub
6. roomfield fusion
7. Quest operator visor read-only overlay
8. speaker policy gate
9. operator-confirmed action surfaces
