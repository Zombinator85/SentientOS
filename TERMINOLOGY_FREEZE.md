# Terminology Freeze and Change Policy

This policy locks the semantics of high-risk terms. Reinterpretation without review is a breaking change.

## Frozen terms
Autonomy; Initiative; Trust; Presence; Resonance; Reflection; Memory; Heartbeat; Goal; Plan; Preference.

## Breaking semantic changes
- Altering the meaning, scope, or exclusions of any frozen term.
- Introducing new usage that conflicts with the frozen definition, even if code behaviour is unchanged.
- Changing wording in ways that shift interpretation without adjusting runtime logic.
- Adding synonyms or metaphor that imply different intent for a frozen term.

## Change process
- Propose a design document describing the required semantic update and why existing definition is insufficient.
- Update `SEMANTIC_GLOSSARY.md` with the revised definition and usage audit notes.
- Notify reviewers via governance channels and include an audit trail entry referencing the proposal.
- Run a terminology audit to confirm all code comments and documentation match the updated meaning.
- Merging requires explicit approval from governance reviewers and amendment of related policy indices.

**Rule:** Changing wording without changing behaviour can still be a breaking change.
