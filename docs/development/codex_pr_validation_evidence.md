# Codex PR Validation Evidence Verifier

Metadata-only verifier/builder that checks proposed Codex PR metadata claims against matrix JSON evidence.

## Scope
- Verifies PR metadata contract (title/body markers/intended title).
- Requires matrix evidence artifact.
- Cross-checks matrix status, required_failure_count, and required validation lanes.
- Supports docs bootstrap+recheck recovery path.
- Rejects local/touched-only claims.

## CLI
- `python scripts/codex_pr_validation_evidence.py verify --title ... --body ... --matrix-json-path ...`
- `python scripts/codex_pr_validation_evidence.py build --matrix-json-path ...`
