# Bounded offline local runtime installation

This boundary consumes a selected runtime provisioning plan, its verified content-addressed runtime escrow, a selected five-wheel dependency plan, its verified bundle escrow, an exact observed Python environment, and explicit operator confirmation. It creates a private stdlib `venv` beneath the SentientOS user-data directory and atomically publishes it only after metadata and every installed distribution `RECORD` have been verified.

The installer is not a resolver. It admits exactly the five dependency wheel paths in canonical plan order followed by the `llama-cpp-python==0.3.35` wheel. Pip runs by absolute interpreter path, with isolated modes, `--no-index`, `--no-deps`, no cache, no compilation, and no input. Ambient Python and pip configuration authority is removed. It neither accesses a network nor upgrades bootstrap tooling.

Inspection is the CLI default. Mutation requires `--execute` and `--confirm-installation-plan-digest` with the exact digest. Work occurs in a private same-filesystem staging directory; failure removes that staging directory, while atomic rename publishes a complete receipt and environment. Existing targets are never overwritten or repaired and are accepted only after source wheels, receipt semantics, venv isolation, installed metadata, negative authority fields, and all six `RECORD` files are reverified.

## Custody and execution boundaries

Runtime wheel acquired + dependency bundle acquired **does not mean installed**. Installed **does not mean import verified**. Import verified **does not mean backend prerequisites verified**. Backend verified **does not mean model loaded**. Model loaded **does not mean commissioned**.

The receipt can establish `runtime_installed=true` and `package_install_performed=true`. It always records `runtime_import_performed=false`, `runtime_available_for_import=false`, `model_load_performed=false`, `commissioning_performed=false`, and `runtime_execution_authority_granted=false`. No package is imported during verification; only stdlib distribution metadata and installed `RECORD` bytes are inspected.
