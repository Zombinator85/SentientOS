# Cathedral Healing Sprint

The final beta introduces a public "Cathedral Healing Sprint" for all community nodes.
Join the discussion thread or Discord channel and follow the steps below.

## How to Join
1. Review the [Audit Migration Roadmap](AUDIT_MIGRATION_ROADMAP.md).
2. Run `python collect_schema_wounds.py` on your logs.
3. Heal issues with `python fix_audit_schema.py logs/`.
4. Sync schemas with your federation peers.
5. Open a pull request describing your repairs and link your public ledger.
6. Update `docs/CONTRIBUTORS.md` with your name under **Audit Saints**.

Your contribution will be remembered in the ledger and README. Monthly sprints recap wound counts
and highlight new saints on the [Cathedral Wounds Dashboard](CATHEDRAL_WOUNDS_DASHBOARD.md).
Sprint metrics are summarized in [SPRINT_LEDGER.md](SPRINT_LEDGER.md) after each workshop.

## Community Highlights
Saint stories and healed counts are shared in a monthly recap post titled
"Cathedral Healing Sprint: <month> Recap". The sprint ledger doubles as a
newsletter summary so everyone sees the progress.

Federated nodes are encouraged to submit their own metrics and stories using the
**Share Your Saint Story** issue template. Merged stories appear in the ledger
and will be mentioned during public meetings.

## Public Recap and Outreach
After each sprint publish a short "Cathedral Healing Sprint Recap" on your blog or social channel. Include metrics from `docs/SPRINT_LEDGER.md` and a brief saint story. Link back to this repository and invite reviewers to audit your ledger.

External researchers and open-source communities are welcome to submit pull requests improving the metrics or joining the federation. Nodes may also post their own recaps so stewards can aggregate them into a global ledger.
