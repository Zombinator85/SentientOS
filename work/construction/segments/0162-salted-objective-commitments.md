# Sequence 162 — Salt objective commitments and preserve failure causes

Source commit `710846a7708f0f1a6289187051c26286228f6115`, tree `1e67c21c01470218fac24245c1aff670022732aa`.

New objective tasks use a 256-bit random commitment nonce. The public task digest commits to the full oracle only with that nonce; the nonce and task parameters remain in private staged request / immutable plan custody. Public plan digests cover protocol controls and public task descriptors, excluding both the oracle task and nonce. Cognition prompts and upstream evidence receive only the public descriptor and salted commitments. New objective protocol and staged-request schemas are v4 and v2 respectively. Historical v1/v3 protocol, plan, and request verification remain readable through explicit legacy branches.

The A/B model-replacement experiment now recovers the commitment nonce from its exact immutable plan on restart. The canonical model-replacement rehearsal also exposed a failure-cause loss: endpoint identity/currentness failures were durably reduced to a generic incomplete status. The condition journal now retains a bounded machine failure code, and the campaign remains terminal/no-retry while returning that concrete code.

Behavioral evidence: 44 objective/history integration tests passed (84.68s); all 8 model-replacement rehearsal and legacy-request checks passed (2.76s); the targeted currentness no-retry test passed (0.57s). Changed Python and test modules compiled. The complete fixture suites remain synthetic and do not measure real-model learning or production behavior.

No hosted CI was requested or run for this construction commit.
