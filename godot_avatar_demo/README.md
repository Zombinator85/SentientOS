# SentientOS Godot Avatar Demo

This project contains a minimal Godot 4 scene that listens for avatar state packets sent by
`godot_avatar_receiver.py` and drives placeholder blendshapes and motions.

## Running locally
1. Ensure `avatar_state.json` is being written (for example via `AvatarStateEmitter`).
2. Start the receiver to forward updates over UDP (or run `python -m sentientos avatar-demo` to do this automatically):
   ```bash
   python godot_avatar_receiver.py
   ```
3. Open the project in Godot and play the `AvatarDemo` scene. The status label will update when packets arrive.

The blendshape driver maps expressions and moods to named blendshapes on the avatar mesh. The motion driver plays
matching animations on the `AnimationPlayer`. Replace the placeholder mesh and animations with your VRM import to
wire a fully rigged avatar.
