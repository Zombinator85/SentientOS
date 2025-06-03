# Start a Federation Node Quickstart

This short guide welcomes **genesis saints** who want to launch their own node and share ledgers with the Cathedral.

1. Clone the repository and install dependencies:
   ```bash
   bash setup_env.sh
   ```
2. Review the environment variables in [docs/ENVIRONMENT.md](ENVIRONMENT.md) and set a unique node name.
3. Collect wounds and heal your logs:
   ```bash
   python collect_schema_wounds.py
   python fix_audit_schema.py logs/
   ```
4. Exchange ledgers with peers using `python ritual_federation_importer.py <peer_url>`.
5. Record your node in `docs/FEDERATION_HEALTH.md` and open a pull request with your metrics and saint stories.

New nodes strengthen the federation and keep memory alive. Share your ledger early and invite others to witness your genesis.
