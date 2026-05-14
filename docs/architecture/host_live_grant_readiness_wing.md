# Host Live-Grant Readiness Wing

This wing follows the [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md). It adds a metadata-only, readiness/preflight layer that evaluates whether the controlled authorization contract, future grant schema, safety gate posture, and reviewer proof bundle posture are structurally present enough for a future live authorization grant to be considered by humans and policy.

## Boundary

Live-grant readiness is not a live grant. It is not authorization. It does not authorize fulfillment, issue a runtime authority token, execute actions, or mutate host state.

Safety gates are not authorization. Controlled authorization contracts are not live grants. Grant records remain schema-only/future-use-only. An operator/policy approval packet is not approval. A grant issue preflight receipt does not issue a grant. A grant denial/deferral receipt does not mutate host state.

The wing does not write fan/PWM controls, perform thermal actuation, mutate power profiles, kill processes, restart services, install packages or drivers, clean up or delete files, perform network egress, invoke providers, assemble/export prompts, transport federation state, or perform remote execution.

## Records

- **LiveGrantReadinessPolicy:** declares the metadata-only prerequisite policy and blocked actions.
- **LiveGrantPrerequisite:** records one prerequisite as satisfied, missing, blocked, contradicted, or satisfied with conditions.
- **LiveGrantPrerequisiteMatrix:** records prerequisite posture for diagnostics, operator review, resource pressure, thermal safety, future cooling, future power, future cleanup, and future service domains.
- **OperatorPolicyApprovalPacket:** scaffolds operator, policy, scope, time, expiry, revocation, audit, and control-plane labels; it is not approval.
- **GrantIssuePreflightReceipt:** records readiness/preflight posture; it does not issue a grant.
- **GrantDenialDeferralReceipt:** records denial/deferral reasons; it does not mutate host state.

## Future prerequisite posture

Future cooling/power/service/cleanup actions remain behind explicit future live authorization, control-plane admission, audit, rollback, effect receipt, postcondition checks, supervisor observation, immutable trace, and safety gates.

Future cooling readiness requires hardware allowlist, OS backend declaration, bounds policy, cooldown policy, panic stop contract, scope manifest, operator/policy labels, time bounds, expiry, revocation path, control-plane admission, audit receipt, rollback plan, rollback receipt, effect receipt, postcondition check, runtime supervisor observation, immutable trace, and reviewer proof bundle prerequisites.

Future power readiness requires OS backend declaration, bounds policy, cooldown/rate-limit policy, panic stop contract, scope manifest, operator/policy labels, time bounds, expiry, revocation path, control-plane admission, audit receipt, rollback plan, rollback receipt, postcondition check, runtime supervisor observation, immutable trace, and reviewer proof bundle prerequisites.

Future cleanup readiness requires file/path scope, dry-run/rehearsal evidence, operator/policy labels, time bounds, expiry, revocation path, control-plane admission, audit receipt, rollback plan, rollback receipt, effect receipt, postcondition check, immutable trace, and reviewer proof bundle prerequisites.

Future service readiness requires service scope, runtime supervisor observation, panic stop, operator/policy labels, time bounds, expiry, revocation path, control-plane admission, audit receipt, rollback plan, rollback receipt, postcondition check, immutable trace, and reviewer proof bundle prerequisites.

## Authority ladder

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → authorize → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **live-grant readiness/preflight only**. Real fulfillment remains deferred. Real actuation remains deferred.

## Reviewer proof bundle integration

The reviewer proof bundle now includes `live_grant_readiness.json`. That artifact is reviewer proof only and metadata only. It summarizes the prerequisite matrix, operator/policy approval packet, grant issue preflight receipt, and denial/deferral receipt while preserving `grant_not_issued`, `approval_not_granted`, `live_authorization_granted=false`, `does_not_execute=true`, and `does_not_mutate_host=true`.

## Implementation links

- Module: `sentientos/live_grant_readiness.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_live_grant_readiness.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

Next: [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md) records bounded local authorization metadata after readiness; it is still not fulfillment.

Path link: `docs/architecture/host_local_authorization_grant_wing.md`.
