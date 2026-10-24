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
group or other permissions. Windows peer source composition additionally requires
the operator-pinned replay-root identity described below. The explicit replay-owner
API publishes into an already provisioned private local Windows root through
handle-bound no-replace rename, flush, and independent readback; it does not create
Windows directories.
The trust catalog for each peer is read from
`<runtime.root>/federation/peer_trust_catalogs/<peer_id>.json`. Its exact digest and
version must match the protected pin, and it must contain entries for that peer only.
Catalog bytes are public, but the pin file supplies the local operator trust root.

## Windows replay-root identity

On Windows, each peer entry must use pin schema
`sentientos.federation_peer_health_trust_pin:v2` and include `root_identity`. The
operator provisions the private replay directory before composing the source; the
runtime never creates it. `root_identity` binds the peer to that existing directory's
volume serial number and 128-bit file ID:

```json
{
  "root_identity": {
    "volume_serial_number": 123456789,
    "file_id": "00112233445566778899aabbccddeeff"
  }
}
```

The values above are illustrative. `volume_serial_number` is an unsigned 64-bit
integer, and `file_id` is exactly 32 lowercase hexadecimal characters. The
`observe_private_directory_identity` helper returns the identity of an existing
private Windows directory as `(volume_serial_number, file_id_bytes)`; serialize the
second value with lowercase hexadecimal encoding. Store the resulting values in the
private pin file. The pin path and replay root must both pass the Windows private-ACL
checks.

When composing a Windows source, SentientOS compares the pinned identity with the
existing `<runtime.root>/federation/peer_health_replay/<peer_id>` directory. The
identity is checked again when the replay owner reads or publishes records. A missing
directory, a legacy v1 pin, an unavailable identity, or any mismatch fails closed.
On POSIX, the existing v1 peer pin remains supported and does not require a Windows
root identity.

Replay custody is bound to
`<runtime.root>/federation/peer_health_replay/<peer_id>`. The current immutable replay
owner uses POSIX descriptor-bound custody or explicitly provisioned Windows
handle custody. No replay directory is created while sources are composed. The runtime
does not accept new events through this recovery projection; it only reconstructs
claims already present in the local verified replay owner. An empty history remains
an empty projection.

The signature verifier proves that an event matches a key in the pinned catalog. It
does not identify who provisioned the pin file, prove a live remote endpoint, make a
peer claim locally true, publish local Health, admit work, plan, execute, or grant
decision authority. Production peers and live Federation telemetry remain
unconfigured unless an operator separately provisions the required local identity,
catalog, replay custody, and source path.
