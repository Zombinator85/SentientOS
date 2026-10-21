# Sequence 537 — enforce canonical campaign protocol contracts

`CampaignProtocol.verify()` previously trusted a self-consistent campaign digest without requiring the fixed aggregation rules and non-claims declared by this campaign schema. It also relied on `create()` alone for trial-ID validation and accepted numerically equal non-integer trial counts. A persisted protocol whose digest and campaign ID were recomputed could therefore change its declared interpretation or contain malformed trial identity values while passing protocol verification.

The verifier now requires the schema's exact aggregation rules and non-claims, a false boolean authority marker, the canonical condition tuple, a strict integer trial count, and the same bounded ASCII trial-ID grammar used by creation. The adverse regression recomputes both campaign digest and ID after each mutation; altered interpretation, unsafe trial ID, float count, and non-boolean authority are still rejected. The exact regression and a hosted-workflow contract test are selected by source validation and produce source-bound acceptance evidence.

Local verification on the committed source content: 63 affected campaign, experiment, production-trial, and end-to-end rehearsal tests passed; the exact new regression plus workflow contract passed (2 tests); compilation, CI YAML parsing, and diff whitespace checks passed. The repository Mypy baseline could not be compared locally because its sanitized toolchain environment cannot see the installed mypy distribution; no Mypy pass is claimed. The exact candidate's hosted CI will run the pinned baseline ratchet and privileged Quality Gate.

The synthetic system rehearsal passed before and after the change. It used isolated temporary installation, governor, and runtime roots. The trial posture remained synthetic and no production model transition, activation, serving, inference, or writeback was performed.

Verified base main: `5b9f7b43bbed42ac2fed43f9db4a73ba427923bc`, tree `15288aa40bcd8cab5bbe71b8ae0531a362a22d3b`
Implementation candidate: `9760cb406396dc663c462b0d39c6c6b4acb8fd76`, tree `9f9a09558272a888fb0b7221eb3bcea1c71304c`
Latest construction segment: `work/construction/segments/0537-enforce-canonical-campaign-protocol-contract.md`
Sequence: 537 (candidate pending hosted verification)
