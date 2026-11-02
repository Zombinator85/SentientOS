# Gaming workload mode

The local chat runtime supports an explicit, reversible `normal` / `gaming`
workload mode. Gaming mode limits each chat invocation to 4,000 input characters,
1,200 output characters, 96 new tokens, and 12 seconds. Existing tighter request
budgets remain tighter. The effective budget and selected mode are included in the
ordinary invocation receipt lineage.

The production chat process exposes the mode through its local chat API. The mode
is process-local and starts as `normal` after restart. A caller must choose
`gaming`; the current runtime does not detect foreground games automatically.
The local chat page also provides a Gaming mode checkbox.
Use `GET /workload-mode` to inspect it and `POST /workload-mode` with
`{"mode":"gaming"}` or `{"mode":"normal"}` to change it. These routes are
available only when the production chat composition is active.
The mode reduces the amount of work a single response can request. It does not
change llama.cpp CPU thread count, reserve CPU or GPU capacity, stop background
inference, observe frame time, or establish hardware suitability. Those controls
need authenticated workload signals and host-side measurements and remain future
integration work.

This is a runtime preference only. It grants no installation, model, host, memory,
input-control, or other actuation authority.
