# Sequence 395: run strict audit before authorized bootstrap

The sequence-394 hosted Required Quality Gate run confirmed that the guarded documentation bootstrap succeeds, then the Administrator audit verifier fails immediately with `verification_checkout_is_not_clean`. The bootstrap's required privilege/covenant ritual records effects in the checkout; placing it before the verifier violates the verifier's clean-candidate precondition.

Reordered the two workflow steps so strict audit and immutability verification run against the untouched exact candidate before docs dependency bootstrap. The bootstrap remains under real hosted Administrator authority and still precedes precommit finalization, which requires MkDocs. Added a workflow contract assertion for the ordering. Authority requirements and audit checks are unchanged.

Local YAML parsing, workflow-order assertion, Python compilation, and `git diff --check` passed. The repository-native pytest attempt was rejected before collection because this isolated checkout is not the canonical editable test install; no test outcome is claimed. Hosted rerun is required. Exact source candidate is parent `1bbd4abd0bb6d33870b9a79b90248f079a06ddba`, tree `297983b58b80346ab7fc8157754d3ca9ba783293`; latest verified main remains `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`. This construction increment is explicitly untested pending hosted checks.

Latest construction segment: `work/construction/segments/0395-audit-before-hosted-bootstrap.md`
