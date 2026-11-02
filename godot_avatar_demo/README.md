# SentientOS Godot Avatar Demo

This project contains a small procedural Godot 4 companion scene that listens for avatar state
packets sent by `godot_avatar_receiver.py`. It renders a lit character with a face and responds to
expression, viseme, and motion fields. A compatible imported model can still use real blendshapes
and authored animation clips through the same adapters.

## Running locally
1. Ensure `avatar_state.json` is being written (for example via `AvatarStateEmitter`).
2. Start the receiver to forward updates over UDP (or run `python -m sentientos avatar-demo` to do this automatically):
   ```bash
   python godot_avatar_receiver.py
   ```
3. Open the project in Godot and play the `AvatarDemo` scene. The status label will update when packets arrive.

The built-in companion is a simple demo character, not a commissioned avatar. Its face uses bounded procedural
scale changes because its primitive meshes have no blendshapes; imported models with named shapes use those instead.
The built-in wave and nod are short procedural gestures because the demo has no authored animation clips; a model
with non-empty `idle`, `wave`, or `nod` clips uses those clips. These adapters do not infer emotion or decide when
to speak. They only render state supplied by SentientOS.

The scene is a standalone preview window. It does not create an in-game overlay, inspect game frames, measure frame
time, or throttle host/GPU resources. Those capabilities require separate platform and operator integration.
This demo is not a production renderer and does not activate or adopt an avatar body.


The demo receiver binds its UDP port to `127.0.0.1` explicitly. It is a
same-host convenience channel, not an authenticated network bridge; do not
change its bind address or expose the port to a LAN.
