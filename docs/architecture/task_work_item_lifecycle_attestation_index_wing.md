# Work Item Lifecycle Attestation Index Wing

`sentientos/work_item_lifecycle_attestation_index.py` and `scripts/build_work_item_lifecycle_attestation_index.py` provide deterministic metadata-only indexing over one-or-more lifecycle final attestation bundles.

This wing only summarizes supplied bundle metadata and optional matrix report status. It never invokes lifecycle action wings, never performs workspace mutation, and only writes an artifact when explicit `--output` is supplied.
