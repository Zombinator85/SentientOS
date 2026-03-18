from __future__ import annotations

from pathlib import Path

from scripts.render_remote_smoke_inventory import main


def test_render_remote_smoke_inventory(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "hosts.template.yaml"
    template.write_text(
        """
hosts:
  - host_id: host-01
    address: ${REMOTE_SMOKE_HOST_1}
    user: ${REMOTE_SMOKE_USER}
  - host_id: host-02
    address: ${REMOTE_SMOKE_HOST_2}
    runtime_root: ${REMOTE_SMOKE_RUNTIME_ROOT}/host-02
""",
        encoding="utf-8",
    )
    output = tmp_path / "hosts.rendered.yaml"
    monkeypatch.setenv("REMOTE_SMOKE_HOST_1", "10.0.0.11")
    monkeypatch.setenv("REMOTE_SMOKE_HOST_2", "10.0.0.12")
    monkeypatch.setenv("REMOTE_SMOKE_USER", "runner")
    monkeypatch.setenv("REMOTE_SMOKE_RUNTIME_ROOT", "/tmp/ci-remote")

    rc = main(["--template", str(template), "--output", str(output)])
    assert rc == 0
    rendered = output.read_text(encoding="utf-8")
    assert "10.0.0.11" in rendered
    assert "runner" in rendered
    assert "/tmp/ci-remote/host-02" in rendered
