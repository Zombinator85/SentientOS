# Sequence 906: require causal-introspection capture tick

A runtime capture accepted an empty tick and later emitted owner observations with an empty `observed_at` value. Capture now rejects a missing or empty tick before reading history or invoking providers; projection and snapshot validation independently reject empty temporal identities so persisted state cannot bypass the boundary. Regression tests cover both capture and projection creation.

Candidate implementation: `ea763cd43ed9497e446e32ce70a55fcd94286f6b`, tree `63377736977c6f0cc8bb7235b444e12099b28e8e`, based on verified main `969639a421a09a9e2ec0de4becf2a937c9f3f6ef`, tree `3b9a71acf66dd4ffadd5fdc801abf5450e3049cb`. Focused causal-introspection, composition, and runtime-closure tests passed 77/77 with zero failures or skips; mypy passed; the documented docs extra built 617 pages. Hosted acceptance remains pending for the combined candidate.

Evidence record: `work/construction/evidence/0906-require-causal-introspection-capture-tick.json`.
