# Authoritative deployed catalog consumer custody

Production selection reconstructs a read-only proof from an authenticated
`InstallationStateHandle`. Under the installation's canonical catalog lock it reads
the authoritative catalog, immutable deployment receipts, and the receipt's terminal
transaction finalization. Schema validity alone and caller-supplied catalog bytes are
only preview provenance.

Equivalent witnesses for the same catalog are ordered lexically by receipt and
transaction identity; this is a canonical witness choice, not a claim of recency.
The lock is released with the frozen snapshot before selection, provisioning,
acquisition, or commissioning work begins.

The proof grants no deployment, acquisition, commissioning, activation, inference,
provider, credential, or other runtime authority. Executable acquisition separately
requires its existing authorization and immediately reconstructs current custody;
stale or caller-supplied provenance fails before transport.
