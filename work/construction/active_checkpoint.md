# Active construction checkpoint

- Verified source: `5394c8595177ae920353c2ec2a1f1fd03dc34e0f`, tree `21f5820ef3e0882d1f4630bf9bb4b666e0bd559d`.
- Latest continuation segment: sequence `25`, `work/construction/segments/0025-smoke-workflow-gates.md`, SHA-256 `cfdfa4432d66f8cdc149caad11935ed36f373378ebfe10da61d0341751d3dd54`.
- The prior head's unprivileged source-validation job and Helm smoke both passed. Artifact emission now uses module entrypoints, requires the manifest inputs, successfully uploaded the exact-source doctrine bundle, and records the protected Forge approval denial as a GitHub warning. The self-check and docs jobs still fail at administrator-only operations; they were not bypassed.
- Exact local results: 27 focused workflow/custody/manifest tests passed; 21 chat-recovery tests passed; targeted mypy clean on the recovery, manifest, and custody-verifier modules. The frozen journal and all 25 compact continuation segments pass the read-only integrity verifier.
- The remote-smoke and Forge-smoke runs on the previous source had zero jobs and failed because job-level conditions referenced unavailable `secrets`/`env` contexts. They are now gated by explicit repository variables; the remote credential step checks missing values without logging them. No remote host, credential, or Forge runtime was invoked locally.
- Next: publish the smoke-gate correction with expected-head CAS, inspect fresh CI, then continue classification of the historical dirty source artifacts and any remaining exact-source acceptance failures.
