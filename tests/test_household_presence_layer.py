from sentientos.household_presence_layer import build_default_household_presence_layer, validate_household_presence_layer

def test_default_build_and_deterministic_digest() -> None:
    a = build_default_household_presence_layer(); b = build_default_household_presence_layer()
    assert a["deterministic_digest"] == b["deterministic_digest"]

def test_policy_expectations() -> None:
    layer = build_default_household_presence_layer()
    assert layer["wildlife_ledger"]["named_profiles_allowed"]
    assert layer["wildlife_ledger"]["example_profile"]["nickname"] == "Fat Boi"
    assert layer["adult_private_context"]["allowed"]
    assert layer["adult_private_context"]["child_visible_blocked"]
    assert "raw_video_retention" in layer["protected_care_zone"]["blocks"]
    assert layer["speaker_boundary"]["recognized_household_address_mode_allowed"]
    assert layer["speaker_boundary"]["nuisance_confrontation_blocked"]
    assert "neighbor_zone_modeling" in layer["wifi_rf_roomfield"]["blocked"]
    assert not layer["jurisdictional_discernment"]["live_lookup_performed"]
    assert layer["external_authority"]["automatic_contact_blocked"]

def test_validation_ok() -> None:
    assert validate_household_presence_layer(build_default_household_presence_layer())["ok"]
