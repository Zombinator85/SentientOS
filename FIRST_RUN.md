# First run: reviewer and contributor path

SentientOS installs a hosted development/runtime package. Installation does not commission a resident, acquire or activate a model, issue authority, install a service, enable egress, or perform host effects.

```bash
git clone <your-fork-url>
cd SentientOS
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e '.[codex]'
python -m scripts.run_tests -q
```

For ordinary runtime exploration, start with [`docs/USAGE.md`](docs/USAGE.md). Model supply is a governed lifecycle—curation, publication authorization, publication, catalog deployment authorization, deployment, acquisition, commissioning, activation, serving, and separately admitted inference—not direct placement of an arbitrary model file.

Contributors must use the current [`AGENTS.md`](AGENTS.md) hot path and canonical [validation and landing contract](docs/development/codex_validation_and_landing_contract.md): clean/fresh SHA, bootstrap, bounded implementation, exact-node acceptance where required, focused proof, matrix, typing/docs/audits/immutability checks, two-phase finalization, one commit, metadata guard, byte-bound PR body, and publication handoff. A repository-ready handoff is not hosted publication custody.
