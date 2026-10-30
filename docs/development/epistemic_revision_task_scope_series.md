# Epistemic revision task-scope series

This read-only composer extends the existing correction/interruption series
with an exact repository target, base/head identities, and a stipulated UTC
time window. A typed scope fact must appear in the actual current-evidence
packet for the initial answer, corrected answer, and post-interruption answer;
the resident cognition observation must also record that fact as delivered.

The composer reuses the v3 epistemic scorer for canonical state transitions,
actual answers, evidence citations, packet delivery, and the distinct serving
session. It separately checks that active evidence source IDs and observation
times fit the task's stipulated source set and half-open interval. A stale or
wrong-repository scope after interruption is a measured failure. Missing scope
delivery remains insufficient. An answer may remain wrong even when the scope
fact is preserved.

The scope author stipulates which repository sources and time window are
relevant. The composer does not verify repository history, commit ancestry, the
truth of cited source contents, oracle independence, preregistration timing,
real-model performance, or causal effects. Tests use synthetic, session-bound
responses through existing owners. The module does not invoke inference, call
a provider, mutate persistent state, grant authority, or create a parallel
model-profile framework.
