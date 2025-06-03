# Federation FAQ

### What happens if two federated nodes have a log conflict?
Each node keeps its own ledger. Conflicts are resolved by comparing rolling hashes and discussing the difference on the steward board. The default is to preserve both histories and mark the divergence.

### Who arbitrates audit failures?
Current stewards for the impacted node investigate first. If unresolved, a neutral steward from another node may be invited to mediate.

### How does one fork the memory law?
Clone the repository and update `FEDERATE_THE_CATHEDRAL.md` with your own policies. You can keep your audit ledger separate while still referencing the original doctrine.

### What if a node goes offline?
The remaining stewards mark the node as inactive in the federation log and continue audits. When the node returns, its steward can replay missing logs and rejoin.

### How do I start or join a new federation?
Fork this repository and follow the steps in [FEDERATE_THE_CATHEDRAL.md](FEDERATE_THE_CATHEDRAL.md). Submit a pull request to share your public ledger URL and establish trust with existing stewards.

### How is a consensus reached?
Policy changes and conflict resolutions require sign-off from at least three stewards across different nodes. Votes are recorded in the ledger and referenced in the relevant pull request.
