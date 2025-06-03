# Federate the Cathedral

This guide describes how to adopt SentientOS memory law and audit tools in new communities.

## Step-by-Step
1. **Clone and Review** – fork or clone this repository. Study `AGENTS.md` to understand required privilege banners and see `STEWARD.md` for rotation duties.
2. **Configure Trust** – edit your environment so `FEDERATION_PEER` and other tokens point to your organization. Nominate at least one steward with signing keys.
3. **Initialize Ledgers** – copy `logs/` to your instance or create new empty ledgers. Run `python verify_audits.py logs/ --repair` to ensure a clean baseline.
4. **Nominate Stewards** – add new steward entries to `CONTRIBUTORS.md` and announce them in your community. Stewards sign the first audit verifying the clone.
5. **Sync or Stay Independent** – decide if your audit ledgers will be merged with upstream or kept separate. The default policy is independent ledgers with optional periodic exports.
6. **Rotate Stewards** – every quarter, rotate stewardship by updating `STEWARD.md` and handing off keys as described in `FEDERATED_STEWARD_EXCHANGE.md`.

Use this procedure as the default federation policy and adapt it as your community grows.
