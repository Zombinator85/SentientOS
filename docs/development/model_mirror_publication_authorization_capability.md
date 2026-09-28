# Model-mirror publication authorization definition

`sentientos.model_mirror.publication_authorization.issue` is registered governance
metadata with a bounded deterministic runtime issuer. Registration does not grant
the issuer, create runtime authority, issue a grant or lease, or perform publication.
Runtime issuance requires exact external approval and real ControlPlane admission; see
[`model_mirror_publication_authorization.md`](model_mirror_publication_authorization.md).

The intended separation is:

```text
independently supplied operator approval
        ↓
bounded publication authorization issuer
        ↓
finite revocable grant + narrower lease
        ↓
existing deterministic publication controller
        ↓
separately admitted publication effect
```

The issuer is limited to reading exact operator approval, the exact curator
publication package, and one immutable publication intent, then producing bounded
grant, lease, and immutable issuance-receipt evidence. Its target is the existing
`sentientos.model_mirror.publish` capability, `deterministic_publication_controller`,
and that capability's exact registered effect set. Issuance is not publication; the
publication controller remains the sole owner of the separately admitted sovereign
publication effects.

Curator approval and artifact possession establish neither issuance nor publication
authority. Publication success does not grant catalog deployment. Provider
configuration and credentials remain separate from definition registration,
authorization issuance, and publication evidence. This task performs no provider,
credential, network, publication, catalog, acquisition, commissioning, activation,
inference, Git, shell, or arbitrary-filesystem effect.

The registration approval is metadata-only evidence bound to the exact canonical
definition digest and registration task identity. It is not runtime publication
approval. The runtime implementation independently requires operator approval,
curator-package and publication-intent identity, a finite revocable grant, a lease no
broader than its grant, `LOCAL_AUTHORIZATION_GRANT_ISSUANCE` admission, separate
publication-effect admission, no credential disclosure, and a durable issuance
receipt.
