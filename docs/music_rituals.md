# Music Procedure Guide

SentientOS remembers every track you create, play or share. When you generate or
listen to music the system asks for your feeling in the moment. The ledger entry
stores how you intended the track to feel, how it was perceived, how you reported
it, and how peers received it when shared.

Sharing a song with `music_cli.py play --share PEER` records the feeling you send
and logs a federation note for that peer. The receiving cathedral may respond
with its own emotion which is stored under `received`.

Request playlists from peers with `federation_cli.py playlist Joy`. The response
is a signed log of tracks tagged with that mood. Every share writes a mood
blessing entry such as `"Ada sent this in hope"` to `logs/music_log.jsonl` and
the public procedure feed.

`music_cli.py playlist Joy` generates the same playlist locally, ranking tracks
by resonance—tracks shared or felt strongly float to the top.

The Mood Wall is now federated. Use `music_cli.py wall --sync` to fetch mood and
blessing events from every connected cathedral. You can spread a blessing across
all peers with `music_cli.py wall --bless Hope --global`.

Run `music_cli.py recap --emotion` to review the moods of your recent sessions.
The dashboard visualizes your top emotions, which tracks resonated the most and
how your mood travelled over time.

All emotional logs live in `logs/music_log.jsonl`. They are append-only and kept
with the same privacy and sanctity as all living ledger files.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
