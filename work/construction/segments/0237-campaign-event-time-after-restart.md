# Sequence 237 - Campaign event time after runtime restart

A fresh process loaded the digest-bound campaign selection, reconstructed its read-only owner, and evaluated the actual runtime signal plane. The resulting signal retained the durable campaign completion time and result digest; adoption and repository mutation remained false. This closes a restart/event-time check within Program A while runtime owner ordering and prior-tick exclusion remain open.

Validation: the fresh-process restart check and the admitted selected-campaign runtime check passed. Python compilation and `git diff --check` passed.

Next: finish Program A's owner ordering and prior-tick boundary, then exercise the later maintenance candidate path using retained adverse and corrective history.
