# Sequence 562 — terminate supervised descendants after the root exits

A controller exception during output handling could leave a descendant running if the supervised root had already exited while that descendant still held the inherited output pipe. The exception path previously skipped process-group cleanup when polling found the root gone. On POSIX, controller exceptions now terminate the recorded process group even after root exit; Windows retains its existing root-process cleanup path.

The regression starts a descendant that inherits the output pipe, confirms the root exits before an injected callback exception, then verifies the descendant cannot write its delayed marker. The exact regression is included in hosted Quality Gate acceptance.

Local source validation: Python AST parsing passed for the supervisor, regression module, and workflow acceptance contract. Hosted Quality Gate ran all 47 exact source-bound call-phase nodes: 47 passed, 0 failed. The new controller-exception regression passed.

Hosted candidate checks passed: CI, strict Administrator Quality Gate, Invariants, Lint Benchmark, Release, Windows Custody, Docker Image, Codex CI, and Gradient null regression. The Quality Gate confirmed hosted pre-commit finalization, candidate finalization, and the separate PR metadata guard. The PR was merged normally. The merge commit has the same tree as the verified candidate; GitHub comparison returned no changed files.

Verified main: `6e150525bfda1ee0778afde25fed0b4909a8cd5e`, tree `d935a7c5c9d12148e1dbaec108d315508fc99bae`
Latest construction segment: `work/construction/segments/0562-cleanup-descendants-after-root-exit.md`
Sequence: 562 (verified merge reconciliation)
