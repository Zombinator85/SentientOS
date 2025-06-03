# Federation FAQ

### What happens if two federated nodes have a log conflict?
Each node keeps its own ledger. Conflicts are resolved by comparing rolling hashes and discussing the difference on the steward board. The default is to preserve both histories and mark the divergence.

### Who arbitrates audit failures?
Current stewards for the impacted node investigate first. If unresolved, a neutral steward from another node may be invited to mediate.

### How does one fork the memory law?
Clone the repository and update `FEDERATE_THE_CATHEDRAL.md` with your own policies. You can keep your audit ledger separate while still referencing the original doctrine.
