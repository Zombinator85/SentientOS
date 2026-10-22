# Active construction checkpoint

## Current verified state — sequence 584

Sequences 582–584 integrate deterministic least-generation-first scheduling and reconcile its source and hosted evidence. The equal-tick, after-restart regression passed. PR #2622 and its evidence follow-up passed the full hosted check set; main matches the verified evidence merge tree. The source changes keep omission evidence and existing admission boundaries.

Latest verified main: `debcec58ba4677c4efdb48375994e5d19f9015cf`, tree `dd188880b1ab36eb52032164cf5bbdb80fdcf11d`
Latest construction segment: `work/construction/segments/0584-reconcile-sequence583-integration.md`
Latest segment SHA-256: `71923dfb3fd0509bcb334dfc05eae5cfccf7774dbab4cb8ee50b209988f62f50`
Sequence: 584 (verified evidence integration)

Next: verify bounded fairness with unequal active-binding counts and ensure only persisted state generations, not evidence volume or omitted attempts, influence service order. The current configured proposition cap and active-evidence bound should constrain worst-case work.
