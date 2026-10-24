# Federation peer Health recovery

Peer Health claims are optional, authenticated read-only projections. They remain
separate from this node's Health, work admission, planning, execution, and decision
authority. Runtime startup configures no peer Health source by default, and the
recovery path adds no network listener or transport.

## Explicit installation pin

An operator may set `federation.peer_health_trust_pin_path` in runtime configuration.
The setting is opt-in. Runtime startup then requires the Federation feature to be
enabled and every pinned peer ID to match a peer configured in the same Federation
configuration. Missing files, malformed pins, changed catalogs, and unknown peers
fail closed.

The pin file is canonical JSON with schema
`sentientos.federation_peer_health_trust_pin:v1`. Each peer entry binds a catalog
version and SHA-256 digest to a bounded freshness interval:

```json
{
  "schema": "sentientos.federation_peer_health_trust_pin:v1",
  "peers": [
    {
      "peer_id": "peer-one",
      "catalog_version": 4,
      "catalog_digest": "sha256:<64 lowercase hex characters>",
      "max_age_seconds": 300
    }
  ]
}
```

The pin file must be an absolute, regular, non-linked path secured for the runtime
identity. On the supported POSIX path it must be owned by the current user with no
group or other permissions. The shared handle reader can check the Windows ACL shape,
but peer source composition currently fails closed on Windows because the replay owner
does not yet provide immutable Windows publication. The trust catalog for each peer is read from
`<runtime.root>/federation/peer_trust_catalogs/<peer_id>.json`. Its exact digest and
version must match the protected pin, and it must contain entries for that peer only.
Catalog bytes are public, but the pin file supplies the local operator trust root.

Replay custody is bound to
`<runtime.root>/federation/peer_health_replay/<peer_id>`. The current immutable replay
owner requires POSIX descriptor-bound private custody; configuring peer Health
recovery on a platform without that owner fails closed. No replay directory is
created while sources are composed. The runtime does not accept new events through
this recovery projection; it only reconstructs claims already present in the local
verified replay owner. An empty history remains an empty projection.

The signature verifier proves that an event matches a key in the pinned catalog. It
does not identify who provisioned the pin file, prove a live remote endpoint, make a
peer claim locally true, publish local Health, admit work, plan, execute, or grant
decision authority. Production peers and live Federation telemetry remain
unconfigured unless an operator separately provisions the required local identity,
catalog, replay custody, and source path.
