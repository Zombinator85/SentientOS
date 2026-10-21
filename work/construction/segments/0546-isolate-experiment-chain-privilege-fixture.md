# Sequence 546 — isolate experiment-chain privilege guards in unit tests

The first exact-candidate hosted Required Quality Gate confirmed all strict Administrator audits passed, then exposed that the new exact experiment-chain nodes use `experiment_tracker` persistence without stubbing its Administrator and Lumos guards. The unit-test fixture now stubs those two guards on the isolated tracker module, matching the test-only pattern in the existing tracker tests. No production authorization code or gate was changed.

The initial exact-candidate Quality Gate run (`39605893385`, PR event; `39605828740`, branch-push event) failed at the three newly selected nodes before the behavior assertions ran. The test runner showed `SystemExit: Access denied` from the production persistence guard. The source correction is now in candidate commit `cc93441bc390997bf2139e881b47b0f981f891ce`, tree `98b2b5caadf2513cdfec33a4599909d52a6f4a2b`; fresh exact-candidate hosted checks are pending. No failed test is counted as a pass.

Verified predecessor candidate: `bf94c77571c6b6eae017db3f38f21fcd19da20f0`, tree `4d0836c6989d462bae682192a4d5d32a0d66c7ec`
Corrected candidate: `cc93441bc390997bf2139e881b47b0f981f891ce`, tree `98b2b5caadf2513cdfec33a4599909d52a6f4a2b`
Latest construction segment: `work/construction/segments/0546-isolate-experiment-chain-privilege-fixture.md`
Sequence: 546 (candidate pending hosted verification)

The fixture change is confined to test setup. Production Administrator and Lumos authorization boundaries remain intact.
