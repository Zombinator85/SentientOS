# Sequence 185 — Resume multi-trial response-journal recovery

Starting evidence HEAD: `1ae45cdd776c56ef9909cefaaa3b3f8fd5eade4b`, tree `64b35fc7f158af93ea09a1134754b52d299d871f`.

Added a continuation chronology to the existing multi-situation response-journal test. It scores the initial partial journal with an explicit 0/2 task denominator, rejects an attempt to replace an already recorded packet response, records the remaining responses, reconstructs the complete set, and compares the resumed aggregate digest with the original full response set.

The source uses the existing create-once journal, preregistration binding, scorer and packet identities. No response is replayed or invented. No source behavior, admission rule, execution authority, or production path changed.

Source commit: `4a6551a027db4ce735686a4bcfe80206541507e2`; tree `7f568ef601b3e5e2546dce48f9212066664f3d34`.

Validation: changed files compile and `git diff --check` passes. Focused tests could not collect: direct pytest is absent and the repository runner stops at its import airlock because `jinja2` is missing. This increment is therefore marked **[untested]**. The exact source tree and changed test blob were independently read back from GitHub.

Next dependency: exercise independently attributed multiple historical consequence events with event-level applicability preserved; maintain explicit uncertainty for unverified applicability.
