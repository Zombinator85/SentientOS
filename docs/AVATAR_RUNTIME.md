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
- `is_speaking`: boolean flag indicating whether the speaker is active.
- `viseme_timeline`: ordered viseme events (`time`, `duration`, `viseme`) for lip-sync playback.

The emitter writes `avatar_state.json` into the SentientOS data directory
(`sentientos.storage.get_state_file("avatar_state.json")`). Downstream systems
may tail the file to drive blendshapes, emojis, or symbolic gestures.

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

## Safe embodiment guidance

- Treat `mood` and `intensity` as advisory, not prescriptive; never force an
  irreversible animation based on a single update.
- Map `expression` to your renderer’s vetted blendshape list; ignore unknown
  labels.
- Use `motion` for symbolic gestures only (e.g., `nod`, `wave`) and avoid
  locomotion that could imply agency without consent.
- When in shared or networked contexts, log downstream actions so they remain
  auditable alongside the SentientOS state trail.
