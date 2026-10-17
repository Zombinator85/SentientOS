# Active construction checkpoint

Sequence 323 repairs Dependabot's parser failure on `requirements-extras.txt`: INI-style headings are comments and the active dependency set remains intact. The exact required-node regression passed with 9/9 dependency-bootstrap contract tests; bootstrap summary, task acceptance, compilation, and diff checks passed. Hosted PR and post-merge validation for this increment are pending.

Source `main` at construction: `1bb5a004e263e0fa13fd20c1dd8ab5d93fc9cf74`, tree `fe24d3600ac802bf58d0e784f113ea8570a44661`. The local test checkout was `08179763200d24c406da2bebb6b5e1ea52f0c65e`, tree `b152d3f309a28f27c6d398acd991592f0ce8ed70`, with the task source staged. Git transport was unavailable; exact current main and file identities were read from GitHub.

The prior sequence 322 is merged as PR #2321. Its first two strict QG attempts failed title binding after strict audit and acceptance passed; corrected QG run `39072543856` passed. On current main, QG, invariants, Codex CI, and docs deploy passed; CI and Docker were still running when this checkpoint was prepared. The hourly Federation Health run for current main and Nightly Audit Integrity remain unobserved.

The previous cleanup incident deleted `sentientos_data/vow/keys/salt.key`; original bytes remain unrecovered and no replacement/rotation was created. Production transition restart remains fail-closed pending process-generation termination and no-inflight evidence; stage replay remains forbidden. Changed-output Federation fixture awaits authorized dispatch. Nightly privileged workflows still require repair. Sequence 286 loss remains documented; stale sequence-178 workspace remains untouched.

Latest construction segment: `work/construction/segments/0323-repair-dependabot-requirements-manifest.md`
Sequence: 323
Segment SHA-256: `75169581e0e55bfe225432172fe7558ceeb0386e4e60f7112a2ffa925dc42a28`
