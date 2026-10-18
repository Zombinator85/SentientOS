# Sequence 397: preserve metadata guard failure reasons in hosted logs

Sequence-396 Required Quality Gate run `39162397893` passed strict audit, immutability, the exact 29-node acceptance, and both landing finalizer phases (`ready_to_commit`, then `ready_for_pr_metadata`). The PR metadata guard returned nonzero, but the workflow redirected its JSON to a runner-temp file and `set -e` terminated before printing the guard's reasons. The result artifact exists, but the connector exposes it only as an opaque file reference; the failure cannot be diagnosed from hosted logs.

The guard step now captures its exit status, continues to parse the guard output, prints its exact status and reasons to stderr on failure, and then fails closed. A contradictory ready result with a nonzero process exit also fails. A workflow contract assertion covers the diagnostic path. This changes failure observability only; the guard criteria and success decision are unchanged.

The current candidate remains blocked at the metadata guard. This repair is untested pending its hosted rerun. Parent `b935c6ec34007111df491801ce277f865f434a34`, tree `0fd3cbc04c170217675f09b3776818f33101ad24`; latest verified main `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.
