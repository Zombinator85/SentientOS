# Gaming workload mode

The local chat runtime supports an explicit, reversible `normal`, `gaming`, or
`automatic` workload mode. Gaming mode limits each chat invocation to 4,000 input characters,
1,200 output characters, 96 new tokens, and 12 seconds. Existing tighter request
budgets remain tighter. The effective budget and selected mode are included in the
ordinary invocation receipt lineage.

In Gaming mode, the trusted chat instruction also asks for brief, friendly,
low-distraction replies focused on the player's request. It discourages long
lists and unsolicited advice, and explicitly says that foreground status alone
does not reveal which game is running. The style identifier is recorded in the
invocation lineage. Normal mode leaves the prompt unchanged. This affects replies
to messages the player sends; it does not start conversations or interrupt play.

The production chat process exposes the mode through its local chat API. Its
runtime state resets to `normal` after restart. The local chat page stores the
selected mode and, for `automatic`, the user-entered executable basenames in that
browser origin's local storage and reapplies them when the page reconnects to a
restarted service. This preference is not shared with other browsers or clients.
Select `gaming` to keep the low-work budget active for all new turns, or select
`automatic` and enter one or more Windows executable basenames such as
`ExampleGame.exe`. Automatic mode
compares only the foreground process basename against that explicit allowlist; it
does not read window titles, command lines, or process paths. The local chat page
provides these controls.

While `automatic` is selected, the page refreshes the foreground match status
every five seconds so the displayed state follows changes in the active window.
The model still uses the same read-only foreground check for each new chat turn;
the page poll is display feedback, not a separate source of inference authority.

Use `GET /workload-mode` to inspect the configured and effective mode. Use
`POST /workload-mode` with `{"mode":"gaming"}` or `{"mode":"normal"}` to
select a fixed mode. For automatic mode, include
`{"mode":"automatic","game_process_names":["ExampleGame.exe"]}`. These
routes are available only when the production chat composition is active.

Automatic detection uses the Windows foreground-window process API. On unsupported
platforms or when process observation fails, it chooses the lower-work Gaming
budget and reports that the signal was unavailable. The allowlist and mode are
process-local runtime configuration and reset on restart; the local chat page
restores the browser's preference when available. This feature reduces each chat
turn's maximum work; it does not change llama.cpp CPU thread count, reserve CPU or GPU capacity,
stop background inference, observe frame time, or establish hardware suitability.
Those need host-side scheduling and performance measurements and remain future
integration work.

This is a runtime preference only. It grants no installation, model, host, memory,
input-control, or other actuation authority.
