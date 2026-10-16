## 2026-10-12 — repair smoke-workflow job conditions

- Fresh Actions on `5394c8595177ae920353c2ec2a1f1fd03dc34e0f` showed the remote-smoke and Forge-smoke workflow runs concluding failure with zero jobs. Their `jobs.<id>.if` expressions referenced the `secrets` and `env` contexts, which are unavailable in that job-level condition position.
- Replaced both conditions with explicit repository-variable opt-ins. The remote smoke now validates its required secrets in a step after opt-in, reports missing configuration without exposing secret values, and does not start an SSH scenario without all four values.
- Focused workflow and custody/manifest tests: **27 passed** with `python -m scripts.run_tests -q tests/test_github_hosted_acceptance_workflows.py tests/test_construction_continuation_custody.py tests/test_contract_manifest_emission.py`. Continuation custody verifier remains ready across 24 segments; changed Python compiles.
- Awaiting hosted execution of the corrected smoke gates. Remote hardware and credentials were not used.
