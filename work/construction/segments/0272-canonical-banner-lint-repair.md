# Sequence 272 — Canonical banner and lint repair

The sequence 271 hosted run repeated the required-root success, but Lint Benchmark found that the new CLI test's hand-copied ASCII banner differed from the configured banner by one character. The source has now been regenerated from `privilege_lint_cli.DEFAULT_BANNER_ASCII`; the targeted repository privilege linter passes on the exact module. The local linter's whole-tree scan also sees unrelated installed packages in this checkout's `.venv`, so the recorded source check targets the changed test module, while hosted CI remains the whole-tree authority.

The daemon planning feedback test uses its own temporary RuntimeGovernor, ControlPlaneKernel, and HostResourceRuntimeCoordinator. It passes alone. The full focused selection passed after the exact banner repair (135 passed, 0 failed), and the exact acceptance manifest verifies 17 of 17 required nodes against the new run provenance.

Validation of this correction: focused linter passed, compileall and diff checks passed, targeted CLI mypy passed. Sequence 271's required GitHub Quality Gate passed at UID 0 on tree `0ecb531de79f37aae39a9f369e5f90cb8557cd72`; the CI lint failure is recorded without rewriting that prior evidence.

