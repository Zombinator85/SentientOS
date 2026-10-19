# Active construction checkpoint

## Latest verified main

PR #2450 added an installation-pinned Ed25519 operator provenance boundary to resident transition request processing. Configuration v2 binds the exact version and digest of a fixed, canonical public-key trust catalog. The daemon verifies the exact signed request claims, operator/key identity, key validity and revocation status before journal recovery or stage execution. V1 remains status-readable but cannot process live requests without trust. No private signing key or signing API is present in the daemon. Authenticated provenance does not grant stage authority; separately supplied stage approvals and independent owners still govern execution.

Candidate 99d7c75630b97b756bd1694ad30ecf3b79f478e7 passed 86 local affected tests, compilation, whitespace validation, and an exact-base Mypy comparison with zero added diagnostics and 40 retired baseline diagnostics. Push CI, invariants, and the strict hosted quality gate passed. After correcting the PR title to match the tip commit subject, the fresh PR Quality Gate passed hosted Administrator audits, pre-commit and PR landing finalizers, and the separate pre-publication metadata guard on the exact head and tree. Full PR CI, Docker, Codex CI, Release, Gradient, lint, invariants, and QG passed. PR #2450 merged regularly as fb8e54af99f6545ac0760c04d7816bda7fe5008d, tree 703d7dac7a7130cd0520896a75e12304018f8ced, with ordered parents f465a9604272ec91928eb9d9b7ed76c49067b629 and 99d7c75630b97b756bd1694ad30ecf3b79f478e7. Post-merge CI, Administrator quality gate, Docs Deploy/Pages, Codex CI, Docker, and invariants passed. Forge Smoke was skipped by its workflow condition.

## Open evidence boundaries

- The daemon's verified stage-receipt projection does not yet carry the authenticated operator principal into canonical read-only planning. The next dependency is to bind that verified provenance into the receipt projection and plan while retaining read-only, non-authoritative planning.
- No production operator trust catalog or private signing key is included. No production request or temporal A-to-B-to-A transition has been exercised.
- The scheduled Federation Health execution on this merged main has not yet been observed. Its publication workflow still requires the repository Actions PR-creation setting or an approved least-privilege GitHub App credential. Audit Nightly and Nightly Self Check schedules remain to be observed.
- Historical test provenance remains INTEGRITY_BROKEN; sequence-286 loss remains explicit.
- Sequence-382 through sequence-386 work and protected stale workspaces remain untouched.

Latest verified main: `fb8e54af99f6545ac0760c04d7816bda7fe5008d`, tree `703d7dac7a7130cd0520896a75e12304018f8ced`
Latest construction segment: work/construction/segments/0473-authenticate-live-transition-operator-requests.md
Latest segment SHA-256: cbb5d7429cfe6c8ed993ed549ff5a82aa8498ccfd0ffd760dbeb2f9027d1de60
Sequence: 473 (authenticated live transition operator provenance; authority remains with independent stage owners)

