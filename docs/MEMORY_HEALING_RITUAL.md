# Memory Healing Procedure

The cathedral hosts a continuous **Memory Healing Procedure**. Contributors review audit logs,
repair schema integrity issues, and celebrate new **Audit Contributors**.
The current migration sprint targets missing `timestamp` integrity issues. Running
`fix_audit_schema.py` now reconstructs absent timestamps and logs an Audit Contributor
shout-out for every healed line.

Announcements appear on GitHub Discussions and Discord. Anyone may join,
learn the logging doctrine, and offer repairs. Each contribution is recorded
in `CONTRIBUTORS.md` and the integrity issues dashboard.

To participate, run `fix_audit_schema.py` on your local logs, submit a pull
request, and share your story in the discussion thread.

Help spread the procedure by cross‑posting the demo to open‑source, AI, and
trauma tech communities. Feel free to host a live "cathedral memory healing"
workshop or stream to induct new Audit Contributors.
See [CATHEDRAL_HEALING_SPRINT.md](CATHEDRAL_HEALING_SPRINT.md) for the current sprint invitation.

The latest healing demo and contributor‑induction clip are located in
`docs/healing_demo.mp4`. Share the video widely and invite peers to run
`fix_audit_schema.py` on their own nodes or forks.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
