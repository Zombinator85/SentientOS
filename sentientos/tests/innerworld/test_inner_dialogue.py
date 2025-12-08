from sentientos.innerworld.inner_dialogue import InnerDialogueEngine


def test_dialogue_deterministic_templates():
    engine = InnerDialogueEngine(max_lines=3)
    spotlight = {"focus": "tension", "drivers": {"qualia_tension": 1.2}}
    reflection = {"trend_summary": {"volatility": "rising", "focus": "qualia"}}
    cognitive_report = {
        "overview": {
            "qualia_stability": "shifting",
            "ethical_signal": "moderate",
            "metacog_activity": "high",
        }
    }

    lines = engine.generate(spotlight=spotlight, reflection=reflection, cognitive_report=cognitive_report)

    assert lines[0].startswith("Focus on tension due to qualia_tension")
    assert "Recent cycles show" in lines[1]
    assert lines[2].startswith("Identity remains qualia=shifting")


def test_dialogue_max_lines_enforced_and_inputs_untouched():
    engine = InnerDialogueEngine(max_lines=2)
    spotlight = {"focus": "planning", "drivers": {"metacog_density": 0}}
    reflection = {}
    cognitive_report = {"overview": {"qualia_stability": "stable"}}

    spotlight_copy = spotlight.copy()
    lines = engine.generate(spotlight=spotlight, reflection=reflection, cognitive_report=cognitive_report)

    assert len(lines) == 2
    assert spotlight == spotlight_copy
    assert lines[0] == "Focus on planning due to baseline status."
    assert lines[1] == "Recent cycles show stable patterns."
