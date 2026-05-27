# Household Presence Camera Disabled Capture Adapter

This contract defines a deterministic metadata-only boundary between the local adapter shell and any future live adapter implementation.

- It is not live hardware access.
- It models capture requests as metadata only.
- Capture remains unavailable by contract.

## Relationships
- Local adapter shell: provides disabled baseline policy posture.
- Live adapter stub: provides future-facing candidate metadata and proof digests.
- Dry-run adapter and policy chain: required offline proof and policy identity gates.

## Request/Attempt model
Requests include mode, capture intent booleans, proof digests, zone config, policy-chain metadata, and operator confirmation metadata.
Any capture attempt or live hardware request is blocked deterministically.

## Blocked semantics
The adapter blocks capture attempts, capture requests, live hardware requests, raw-media requests/payloads, speaker output requests, external disclosure requests, and missing policy proofs.

## Safety boundary
No camera, microphone, or media stack is used. No media payload is accepted. No subprocess/network/provider behavior is introduced.

## Forbidden next steps
open_camera_now, attempt_capture, enable_live_capture, enable_live_recording, store_raw_media, attach_media_payload, bypass_policy_chain, bypass_zone_config, bypass_dry_run, enable_speaker_output, enable_external_disclosure.

## Future sequence
1. disabled-capture boundary
2. operator review
3. more offline fixture proof
4. future adapter implementation with capture still disabled by default
5. policy-gated live adapter only after explicit future confirmation
