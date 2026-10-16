# Sequence 190 — Score multi-event responses from the write-once journal

Starting evidence HEAD: `53ead93fc754f3af6bc371de9300455a15aea771`, tree `7a77a27736020849194d220afb12e162c809b48c`.

Connected the multi-event packet protocol to the existing response journal and CLI scorer. The builder CLI accepts multiple admitted record IDs plus a separate applicability declaration file; the scorer dispatches by frozen schema version and preserves per-condition raw-output digests, session/settings comparability, event score vectors, and exact omission identities. The response journal now accepts the v1 multi-event preregistration while retaining create-once packet identity.

The CLI integration records only two of three responses, restarts the scorer, and reports a partial/incomparable task with denominator 1. After the final packet is recorded, a fresh CLI process scores 1/1 and preserves the event's unverified applicability state. Adversarial controls cover corrupt journal content, duplicate session use, changed model settings, substituted packets, preregistration mutation, and attempted response replacement.

Validation: 35 embodied/transfer tests passed; source and changed scripts compile; diff checks passed. The journal retains operator-recorded, unauthenticated external-output posture; no fresh model session or backend receipt is claimed.

Source commit: `dccdfdc40fb428d60c9925358e34970424bd7941`; tree `3848ecaa77e10bf66dd57a7610f8bce6a414dd07`. All five changed source/test blobs were independently found in the live tree.

Limit: selection prioritizes unverified operator declarations for bounded inclusion; it does not establish causal applicability. The decision-quality output remains a separate unscored vector.

Next: define a frozen, versioned decision-quality rubric capable of marking a history-present proposal poorly, a withheld proposal well, or all conditions indeterminate, without using treatment labels to derive expected answers.
