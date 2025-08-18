from subprocess import run, PIPE
import json, sys


def test_wdm_cli_smoke() -> None:
    p = run(
        [
            sys.executable,
            "wdm_cli.py",
            "--seed",
            "Seed",
            "--context",
            '{"user_request": true}',
            "--config",
            "config/wdm.yaml",
        ],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
    )
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert out["decision"] in ("respond", "initiate", "deny", "rate_limited")

