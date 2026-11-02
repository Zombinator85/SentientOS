# SentientOS Godot Avatar Demo

This project contains a minimal Godot 4 scene that listens for avatar state packets sent by
`godot_avatar_receiver.py` and drives placeholder blendshapes, visemes, and motions.

## Running locally
1. Ensure `avatar_state.json` is being written (for example via `AvatarStateEmitter`).
2. Start the receiver to forward updates over UDP (or run `python -m sentientos avatar-demo` to do this automatically):
   ```bash
   python godot_avatar_receiver.py
   ```
3. Open the project in Godot and play the `AvatarDemo` scene. The status label will update when packets arrive.

The scene currently provides a packet/status preview with a `BoxMesh`, no blendshapes, and empty animation clips.
The expression and motion drivers are typed adapters: they apply named shapes or animations when the imported
mesh/player provides them, and safely do nothing when those assets are absent. A viseme timeline similarly needs a
mesh with the configured mouth blendshape. This demo is not a commissioned renderer or an embodied production
avatar. Import a compatible rigged model and authored animations before treating expression or motion output as
visually implemented.
