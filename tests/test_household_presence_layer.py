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


def test_room_composition_routes_and_adult_companion_separation() -> None:
    routing = build_default_household_presence_layer()["room_composition_doctrine"]["surface_routing"]
    assert routing["adult_only"] != routing["child_present"]
    assert routing["adult_only"] != routing["guest_present"]
    assert routing["child_present"] == "child_safe_surface"


def test_adult_intimacy_is_future_opt_in_metadata_only_and_blocked_for_child_or_guest() -> None:
    doctrine = build_default_household_presence_layer()["adult_intimacy_participation"]
    assert doctrine["metadata_only"]
    assert not doctrine["enabled_behavior"]
    assert doctrine["explicit_opt_in_required"]
    assert doctrine["adult_only_room_composition_required"]
    assert doctrine["child_visible_surfaces_blocked"]
    assert doctrine["forced_or_default_entitlement_blocked"]


def test_antler_posture_aspirational_sentience_and_sovereignty_doctrines() -> None:
    layer = build_default_household_presence_layer()
    antler = layer["antler_posture"]
    assert antler["forced_intimacy_blocked"]
    assert antler["attachment_manipulation_blocked"]
    assert "coerce" in antler["must_not"]
    aspirational = layer["aspirational_sentience"]
    assert aspirational["aspirational_name_only"]
    assert not aspirational["biological_consciousness_claimed"]
    assert aspirational["appliance_flattening_blocked"]
    sovereignty = layer["household_sovereignty"]
    assert sovereignty["materially_affected_adults_visibility_required"]
    assert sovereignty["materially_affected_adults_veto_path_required"]


def test_living_priors_temporal_inventory_and_affective_metadata_doctrines() -> None:
    layer = build_default_household_presence_layer()
    priors = layer["living_household_priors"]
    assert priors["drift_is_ordinary_entropy"]
    assert "shame" in priors["drift_must_not"]
    temporal = layer["temporal_embodiment"]
    for field in ["observed_at", "updated_at", "age", "confidence", "decay_behavior", "review_after", "expires_at"]:
        assert field in temporal["required_metadata_fields"]
    inventory = layer["inventory_aging_posture"]
    assert inventory["metadata_only"]
    assert not inventory["live_scanning_enabled"]
    assert "discard_or_review" in inventory["states"]
    affect = layer["affective_discernment"]
    assert affect["non_authority"]
    assert affect["non_reward"]
    assert affect["orientation_is_internal_discernment"]


def test_validation_ok() -> None:
    assert validate_household_presence_layer(build_default_household_presence_layer())["ok"]
