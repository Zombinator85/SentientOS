# Task-acceptance behavioral witnesses

This developer-workflow contract supplements the canonical [validation and landing contract](codex_validation_and_landing_contract.md). Witnesses are local evidence, not authority: they do not establish authorship or external authenticity and grant no runtime, repository, provider, network, deployment, merge, or mutation power.

## Schema and canonical form

`sentientos.behavioral_witness:v1` binds the repository SHA, run ID, exact pytest node ID, `call` phase, contract ID, witness kind, facts object, facts digest, and complete digest. Digests use SHA-256 over canonical UTF-8 JSON with sorted keys, compact separators, and non-finite numbers forbidden. `facts_digest` covers only facts; `digest` covers every field except itself.

## Bounds and recorder lifecycle

The `behavioral_witness.record(contract_id, witness_kind, facts)` pytest fixture derives node identity from the current item and repository SHA/run ID from `scripts.run_tests`. Recording is call-phase-only and immediately normalizes and deep-copies facts. Exact duplicates deduplicate; conflicting node/contract/kind records fail the test.

Limits are 32 witnesses per node, 128 per run, 64 KiB canonical facts, depth 8, 256 mapping keys, 1,024 list elements, 4,096 characters per string, and 128 characters for contract IDs and kinds. Only JSON primitives, lists, and string-keyed mappings are accepted. Recursive values, bytes, sets, custom serializers, non-string keys, NaN, infinity, and excesses fail closed.

## Provenance and acceptance

The pytest reporter publishes witnesses, total and per-node counts, an aggregate digest, and reporter status. `scripts.run_tests` validates exact run, SHA, selected node, call phase, call outcome, and digests before copying these fields into hash-chained provenance. Witness-free legacy provenance remains valid.

`sentientos.task_acceptance:v1` is unchanged. A `sentientos.task_acceptance:v2` required-node entry may add `witness_contracts`, each naming an exact `contract_id`, `witness_kind`, and bounded `assertions`. Contracts are additional to file existence, selection, call outcome, reporter completeness, and SHA checks. Limits are 32 contracts per node and 64 assertions per contract.

The closed operators are `equals`, `not_equals`, `is_true`, `is_false`, `is_nonempty`, `count_equals`, `same_value`, `different_value`, and `ordered_subsequence`, addressed with RFC 6901 JSON Pointers. There is no expression evaluation, importing, shelling, regex execution, templating, or callable dispatch; unknown operators fail closed.

Failure classifications distinguish missing, duplicate, conflicting, wrong-kind, wrong-run, wrong-SHA, non-call-phase, digest-invalid, assertion-failed, malformed-contract, and unknown-operator evidence using the `required_witness_*`, `malformed_witness_contract`, and `unknown_witness_assertion_operator` reason families emitted by the verifier.

## Trust boundary

Witnesses seal what a local test reported observing within one repository-native run. They remain evidence rather than policy truth, adoption, consent, external attestation, or execution authority. Landing custody and recovery remain governed by the canonical contracts referenced above.
