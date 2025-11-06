from pathlib import Path


def test_console_mesh_tab_present():
    html = Path("apps/webui/console/index.html").read_text(encoding="utf-8")
    assert "href=\"#mesh\"" in html
    assert "Mesh Overview" in html
    assert "Council of Voices" in html
    assert "id=\"mesh-dream-count\"" in html


def test_console_mesh_scripts_register_handlers():
    js = Path("apps/webui/console/console.js").read_text(encoding="utf-8")
    assert "const meshDreamCount" in js
    assert "function renderMesh" in js
    assert 'source.addEventListener("mesh_update", handleMeshUpdate);' in js
    assert "function handleMeshUpdate" in js
    assert "autonomyStartButton" in js
