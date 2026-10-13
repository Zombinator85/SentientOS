# Sequence 157 — Report whether scored episodes used relevant history

**Source:** `fae8d77d86fcb1ca6b12f058c10fcb54c842f802`  
**Tree:** `a84d707c09c246871028a4bb3ff9f7dc30280d55`

The read-only task-family progression report previously exposed each episode's history record set but did not say whether those admitted records contained evidence declared for that task family or whether present/restored conditions actually retrieved it. It could therefore describe unrelated-history controls as a developmental trajectory without making that limitation visible. The report now verifies history records through read-only writeback recovery, binds each record ID to its digest, identifies admitted facts with the requested family, and records the family-matching IDs retrieved by each condition. No matching family history is reported explicitly; no learning status is promoted.

Focused progression tests passed (**2 passed in 1.62s**) for both a valid-but-unrelated history sequence and an adverse family example retrieved by present/restored but withheld from the control. Changed Python compiled. These are fixture observations, not actual model behavior or performance claims.

Next: use the already implemented source-score projection and ordinary writeback path to exercise a second task instance with explicitly required family history, then inspect if any full episode/restart acceptance gap remains.
