# Sequence 161 — Bind developmental source identity during projection

Source commit `1d23b1eea68127f01910e905ce5618b6f57e6f18`, tree `f0b1b560a617451a39eb248fae995b68fbe45e3a`.

The normal World-State-to-developmental-history projection now requires the run's canonical `developmental-history-run:<run_id>` source identity and matching World-State subject identity/kind. This prevents a valid score or record digest from being transplanted onto an unrelated source row. Focused adversarial cases cover substituted task answer, source ID, and subject ID; the integrated task test also confirms raw oracle field names/values do not enter the cognition prompt.

Validation: two focused behavioral tests passed (103.99s) against the exact isolated construction source; changed Python compiled. These results are construction evidence only. The experiment uses fixture-issued inference receipts; no actual model learning or production behavior was measured.

The review identified a separate privacy defect to address next: task and plan digests are currently unkeyed hashes over low-entropy private oracle fields. Those hashes are exposed to cognition as upstream metadata. Existing protocol history and artifact verification must remain compatible while new task publication stops exposing oracle-derived commitments.
