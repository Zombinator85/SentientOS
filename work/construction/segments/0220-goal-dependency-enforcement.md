# Sequence 220 — Enforce work-plan task dependencies

Work-plan tasks now carry explicit prerequisite identities. The parser accepts older version-one rows with no dependency list, while rejecting duplicate, missing, or forward references. Generated forge-apply tasks depend on the matching validation and proposal tasks. During execution, a failed or unknown prerequisite blocks its dependent with a recorded dependency reason; independent tasks remain eligible to proceed.

Validation: 30 focused plan, executor, goal-state, and execution-journal tests passed. Seven affected Python modules compiled and `git diff --check` passed. Tests cover generated dependency identity, failed validation blocking forge apply, unknown interrupted proposal blocking apply, independent-task progress, and version-one compatibility.

This adds ordering and failure propagation inside the existing bounded executor. It grants no new production, provider, or host-effect authority.
