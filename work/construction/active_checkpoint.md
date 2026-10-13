# Active construction checkpoint

The held-out fixture episode now recovers invocation receipts through the existing installation-scoped canonical reader in a fresh child process. A changed persisted request digest is rejected before any new inference call. Present/withheld/restored fixture scores are 3/3, 0/3, 3/3. Serving custody and invocation receipts are fixture-issued; no real local model behavior or learning is demonstrated.

Latest source commit: eb89f0e942ed5fa408b68be9caeb996f2817c4f8
Latest source tree: 7d4c17c852ba30555ce3681d988be2ef8a437cd0
Latest segment: work/construction/segments/0167-installation-reader-heldout-process.md
Segment SHA-256: 4abc32265004fe0519856475243cdb5313640349679c0394c129ab16b904ce9b
Evidence: work/construction/evidence/0167-installation-reader-heldout-process.json
Evidence SHA-256: fd8f1b8c1c63c210f0c45cad2207c01352d6363d7f1028d841f6e423818fabc1
Sequence: 167

Next: inspect the evidence contract behind `actual_nonsynthetic_inference_verified`; determine whether canonical installation custody distinguishes a fixture issuer from independently observed local-model execution, and keep those claims separate.
