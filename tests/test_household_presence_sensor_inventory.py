from sentientos.household_presence_sensor_inventory import build_default_inventory, dumps_inventory_json


def test_known_surfaces_present_and_classified() -> None:
    result = build_default_inventory(".")
    by_path = {s.repo_path: s for s in result.inventory.surfaces}
    assert "camera_daemon.py" in by_path
    assert by_path["camera_daemon.py"].surface_kind == "existing_live_surface"
    assert "defer_live_runtime" in by_path["camera_daemon.py"].integration_recommendations
    assert "vision_tracker.py" in by_path
    assert "do_not_duplicate" in by_path["vision_tracker.py"].integration_recommendations
    assert by_path["face_emotion.py"].authority_level == "non_authoritative_affect"
    assert "needs_affective_non_authority_check" in by_path["face_emotion.py"].integration_recommendations
    assert by_path["scripts/perception/gaze_adapter.py"].surface_kind in {"existing_metadata_surface", "existing_live_surface"}


def test_docs_schema_and_embodiment_and_host_inventory_present() -> None:
    result = build_default_inventory(".")
    paths = {s.repo_path for s in result.inventory.surfaces}
    assert "docs/PERCEPTION_BUS.md" in paths
    assert "docs/schemas/perception_bus.schema.json" in paths
    assert "sentientos/host_inventory.py" in paths
    assert "sentientos/embodiment/embodiment_daemon.py" in paths
    assert "sentientos/embodiment/embodiment_digest.py" in paths


def test_inventory_json_deterministic() -> None:
    r1 = dumps_inventory_json(build_default_inventory("."))
    r2 = dumps_inventory_json(build_default_inventory("."))
    assert r1 == r2
