# Avatar Runtime

This document outlines how SentientOS exposes avatar state for external renderers
and how to keep the pipeline bounded by doctrine and safety constraints.

## State emission

`avatar_state.py` provides an `AvatarStateEmitter` that serializes:

- `mood`: human-readable affect descriptor (e.g., `joy`, `calm`).
- `intensity`: normalized value (0.0–1.0) clamped for safety.
- `expression`: desired facial overlay (emoji, blendshape label, or stylized cue).
- `motion`: suggested locomotion or gesture (e.g., `idle`, `wave`).
- `current_phrase`: the text currently being spoken (empty when idle).
- `phrase`: structured phrase metadata including `text`, `started_at`, `muted`, `speaking`, and `viseme_count`.
- `is_speaking` / `speaking`: boolean flag indicating whether the speaker is active (set to `False` when muted).
- `viseme_timeline`: ordered viseme events (`time`, `duration`, `viseme`) for lip-sync playback.

The emitter atomically replaces `avatar_state.json` in the SentientOS data
directory (`sentientos.storage.get_state_file("avatar_state.json")`). Its
temporary and resulting files use owner-only permissions on POSIX systems, so
readers never observe a partially serialized state and phrase text is not
world-readable by default. Downstream systems may tail the file to drive
blendshapes, emojis, or symbolic gestures.

The payload always includes a timestamp, resolved runtime mode, and whether the
system is running in `LOCAL_OWNER` mode. External consumers must treat
`LOCAL_OWNER` as an override that can relax semantic constraints but should still
keep gestures non-coercive and reversible.

## Godot runtime

An optional Godot-based runtime is available via
`install_godot_avatar_runtime.sh`, which:

1. Ensures a writable `avatar_state.json` target exists and links it into
   `tools/avatar_runtime` for Godot access.
2. Downloads Godot (if absent) into the local tools directory or reuses a
   system installation.
3. Provides a demo scene placeholder in `tools/avatar_runtime/demo` describing a
   VRM-compatible setup that reads the linked state file.

Launch Godot with the linked demo directory and attach a lightweight script that
applies `avatar_state.json` updates to your avatar rig. The watcher script
requirements (`watchdog`) are already present in `requirements.txt` for use in
Python-side file listeners.

## Explicit local chat companion output

The supervised production chat process can be started with
`--avatar-state-path <local-file>` to configure an output path. Without that
argument, the chat UI cannot publish to the avatar. When configured, the local
chat page offers **Show replies in companion** and the server only starts on a
loopback address. Enabling it creates a
human-approved `AVATAR_EMISSION` grant scoped to that one conversation. The
grant expires after four hours and is discarded when the chat process stops;
turning the control off revokes it immediately. Each emitted turn gets its own
admission record bound to the exact response digest and turn.

The state file is shared, so only one conversation can publish at a time. If an
authorized clear is denied, output remains disabled and the display channel is
reserved until an authorized clear succeeds; the UI reports that pending state.

This path displays the assistant's response text and a neutral nod only. It
does not call TTS, claim that the avatar is speaking, infer the assistant's
emotion, or generate mouth cues. The state file is owner-only on POSIX. Start
the local avatar receiver with the same file path and open the Godot demo to
render updates. The display remains a standalone window, not a game overlay.

For each response, the companion may also receive the effective `normal` or
`gaming` workload mode from the verified local-model invocation receipt. The
Godot demo caps only its own render loop at 60 FPS in normal mode and 15 FPS in
gaming mode. This is a best-effort reduction in companion rendering work; it
does not control game scheduling, model CPU/GPU threads, or overall system
resource allocation. The workload signal still identifies only a configured
foreground executable match, not game content or performance.
While the local visual companion grant is active, the chat service checks the
effective workload mode once per second and updates this renderer hint on a mode
change. Revoking the grant, its expiry, or chat shutdown stops the watcher.

## Optional local spoken replies

The supervised chat process can separately opt into local spoken replies with
`--local-speech-output`. The local chat page then offers **Speak replies with
local voice**. It is off by default and needs a separate per-conversation
`SPEECH_TTS` grant; the grant expires after four hours or when the process
stops. Install the narrow optional dependency with
`pip install -e '.[local-tts]'`. The player uses `pyttsx3` and the host's local
speech engine only. This path does not select Edge TTS, upload text, record a
microphone, or send audio to a provider. When the local backend is missing, the
control remains unavailable. At most one short response waits in the playback
queue; a full queue reports busy instead of accumulating delayed speech.
Disabling the control discards queued replies and requests that active playback
stop.

Speech output is generated audio from text, not live lip-sync evidence. The
avatar's visual chat state and speech playback use separate output paths; the
renderer does not claim mouth motion merely because audio was queued. Gaming
mode still affects the model's reply budget and wording only. It does not
automatically speak, start a conversation, capture game frames or audio, or
control the game.

## Safe embodiment guidance

- Treat `mood` and `intensity` as advisory, not prescriptive; never force an
  irreversible animation based on a single update.
- Map `expression` to your renderer’s vetted blendshape list; ignore unknown
  labels.
- Use `motion` for symbolic gestures only (e.g., `nod`, `wave`) and avoid
  locomotion that could imply agency without consent.
- When in shared or networked contexts, log downstream actions so they remain
  auditable alongside the SentientOS state trail.
# Evidence posture

Avatar state emitted by this compatibility runtime is **commanded output state**,
not observed embodiment. Renderer feedback and independent observation require
separate authenticated evidence envelopes; neither is inferred from a changed
state file or a successful send. The canonical technical body description and
resident bridge are documented in
`docs/architecture/embodiment_self_observation_bridge.md`.

Body artifact creation and current-generation changes use the separate governed
workcell in `docs/architecture/avatar_body_authoring_succession.md`. Adoption can
produce a renderer handoff command, but neither adoption nor command delivery is
renderer-reported or independently observed state. `neos_blender_bridge.py`
remains legacy compatibility and is not an authoring backend.
