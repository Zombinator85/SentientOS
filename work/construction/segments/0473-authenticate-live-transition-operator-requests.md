# Sequence 473 — Authenticate live transition operator requests

## Source increment

Starting from verified main `f465a9604272ec91928eb9d9b7ed76c49067b629`, this increment adds an installation-provisioned Ed25519 provenance boundary to live resident-transition request admission. Live configuration v2 pins the exact version and digest of a canonical, read-only trust catalog at a fixed installation path. Catalog validation rejects duplicate JSON keys, noncanonical encodings, malformed key identifiers, duplicate operator/key tuples, invalid validity intervals, and mismatched digests. The configured digest is the installation trust anchor; a catalog's self-digest alone does not authenticate its provisioning.

The operator signs the exact canonical request claims with a domain-separated payload. The daemon verifies the operator identity, key tuple, request-claims digest, signature envelope, key validity, current revocation state, and Ed25519 signature before journal recovery or stage execution. V1 configuration remains readable for status, but cannot process live requests without an authenticated trust anchor. There is no daemon signing API or private signing key.

The end-to-end rehearsal uses a temporary keypair and catalog containing only the public key. A regression test confirms that a matching journal entry cannot make an unsigned or untrusted request appear recovered. Accepted requests still require the existing stage approval and independent owner checks; authenticated origin does not grant stage authority.

## Local verification

Five affected test files passed: 86 passed. Compilation and `git diff --check` passed. The exact-base Mypy comparison added zero diagnostics and retired 40 baseline diagnostics.

## Hosted verification and merge

Candidate `99d7c75630b97b756bd1694ad30ecf3b79f478e7` has tree `703d7dac7a7130cd0520896a75e12304018f8ced` and parent `f465a9604272ec91928eb9d9b7ed76c49067b629`. Push CI #39341102100, Required Quality Gate #39341102112, and Invariant Tests #39341102204 passed on that exact candidate. The hosted PR Quality Gate used the solo profile; an exhaustive matrix was not requested. Its finalizer artifact confirms the exact candidate and pre-commit acceptance, Administrator-backed strict audits and finalization, plus the separate pre-publication metadata guard. The guard read back the exact head and tree and returned `pr_metadata_guard_ready`.

The first PR Quality Gate attempt stopped before finalization because the PR title still matched the earlier feature commit rather than the added tip test commit. The PR metadata was aligned with the exact tip subject, then fresh QG #39341502176 passed. The source candidate did not change. PR #2450 also passed CI #39341106607, Invariant Tests #39341106594, Docker #39341106591, Codex CI #39341106707, Release #39341106602, Gradient null regression #39341106664, and Lint Benchmark #39341106633. PR #2450 merged using the regular merge method with the expected head `99d7c75630b97b756bd1694ad30ecf3b79f478e7`.

Independent GitHub readback verifies `main` at merge commit `fb8e54af99f6545ac0760c04d7816bda7fe5008d`, tree `703d7dac7a7130cd0520896a75e12304018f8ced`, with ordered parents `f465a9604272ec91928eb9d9b7ed76c49067b629` and `99d7c75630b97b756bd1694ad30ecf3b79f478e7`. Post-merge CI #39341782092, Required Quality Gate #39341782139, Docs Deploy #39341782086, Codex CI #39341782228, Invariant Tests #39341782133, and Docker #39341782125 all succeeded. Post-merge Administrator audits passed. Forge Smoke #39341782109 was skipped by its workflow condition; post-merge finalizers and metadata guard were skipped by event condition. The exact pre-publication guard passed before merge.

## Next dependency and limits

The authenticated request currently binds operator provenance to the request digest and journal link. The next useful increment is to carry verified operator provenance through the daemon's verified stage-receipt projection into canonical read-only planning, while keeping planning non-executing and stage owners authoritative.

No production operator trust catalog or private signing keys are included, and no production request or temporal A-to-B-to-A transition was exercised. Production inference and campaign execution were not initiated. The historical test-provenance integrity break and sequence-286 loss remain explicit. The scheduled Federation Health execution on this merged main has not yet been observed; its publication workflow still needs the repository Actions PR-creation setting or an approved least-privilege GitHub App credential. Sequence-382 through sequence-386 and protected stale workspaces remain untouched.

