# Start a Federation Node Quickstart

This guide helps operators start a federation node using the current,
deterministic operations CLI.

1. Clone the repository and install dependencies:
   ```bash
   bash setup_env.sh
   ```
2. Review runtime/environment options in [docs/ENVIRONMENT.md](ENVIRONMENT.md)
   and set node-specific values.
3. Bootstrap baseline node artifacts:
   ```bash
   python -m sentientos.ops node bootstrap --seed-minimal --json
   ```
4. Validate node and audit posture:
   ```bash
   python -m sentientos.ops node health --json
   python -m sentientos.ops audit verify -- --strict
   ```
5. Run a deterministic federation simulation before joining shared operations:
   ```bash
   python -m sentientos.ops simulate federation --baseline --json
   ```

For public↔internal terminology mapping, see
[PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.
