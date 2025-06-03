# Legacy Test Status

The following tests are currently excluded from CI runs. They either rely on missing
external tooling or contain deprecated modules.

| Test File | Status | Root Cause |
|-----------|--------|------------|
| `tests/test_avatar_genesis.py` | `env` | Requires Blender `bpy` module |
| `tests/test_modalities.py` | `env` | Hardware bridges with syntax issues |
| `tests/test_avatar_rituals.py` | xfail | Avatar retirement code syntax errors |
| `tests/test_avatar_artifact_gallery.py` | xfail | Gallery CLI import fails |
| `tests/test_policy_suggestions.py` | xfail | Missing `review_requests` dependencies |
| `tests/test_federation.py` | xfail | Federation stubs incomplete |
| `tests/test_federation_cli.py` | xfail | Federation CLI modules missing |
| `tests/test_federation_invite.py` | xfail | Invite helpers incomplete |
| `tests/test_music.py` | xfail | Music CLI lacks logging_config setup |
| `tests/test_cli_daemon_admin_banner.py` | xfail | Large CLI list not stable |

Passing tests can be run with:

```bash
bash setup_env.sh
pytest -m "not env"
```

Contributions to repair or remove these legacy tests are welcome. Update this
file as modules are healed.
