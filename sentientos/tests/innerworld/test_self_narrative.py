import copy

import pytest

from sentientos.innerworld.self_narrative import SelfNarrativeEngine

pytestmark = pytest.mark.no_legacy_skip


def test_deterministic_chapter_creation_and_input_preservation():
    engine = SelfNarrativeEngine()
    cognitive_report = {
        "overview": {
            "qualia_stability": "shifting",
            "ethical_signal": "high",
            "metacog_activity": "moderate",
        },
        "trend_analysis": {"confidence": "stable"},
        "insights": [
            "Confidence has remained stable across cycles.",
            "Tension levels are stable.",
            "Ethical conflicts remain low.",
            "Metacognitive note density is stable.",
        ],
    }
    original_snapshot = copy.deepcopy(cognitive_report)

    engine.update_chapter(cognitive_report)
    chapter = engine.get_chapters()[0]

    assert chapter == {
        "chapter_id": 1,
        "qualia_theme": "shifting",
        "ethical_theme": "high",
        "metacog_theme": "moderate",
        "trend_highlights": {"confidence": "stable"},
        "key_insights": original_snapshot["insights"][:3],
    }
    assert cognitive_report == original_snapshot


def test_max_chapters_enforced_with_fifo():
    engine = SelfNarrativeEngine(max_chapters=2)
    base_report = {
        "overview": {
            "qualia_stability": "stable",
            "ethical_signal": "low",
            "metacog_activity": "low",
        },
        "trend_analysis": {},
        "insights": ["Baseline insight."],
    }

    engine.update_chapter(base_report)
    engine.update_chapter(
        {
            "overview": {
                "qualia_stability": "shifting",
                "ethical_signal": "moderate",
                "metacog_activity": "high",
            },
            "trend_analysis": {},
            "insights": ["Shift observed."],
        }
    )
    engine.update_chapter(
        {
            "overview": {
                "qualia_stability": "volatile",
                "ethical_signal": "critical",
                "metacog_activity": "moderate",
            },
            "trend_analysis": {},
            "insights": ["Volatility detected."],
        }
    )

    chapters = engine.get_chapters()
    assert len(chapters) == 2
    assert [chapter["chapter_id"] for chapter in chapters] == [2, 3]


def test_deterministic_identity_summary():
    engine = SelfNarrativeEngine()
    reports = [
        {
            "overview": {
                "qualia_stability": "stable",
                "ethical_signal": "moderate",
                "metacog_activity": "low",
            },
            "trend_analysis": {},
            "insights": ["Confidence steady."],
        },
        {
            "overview": {
                "qualia_stability": "stable",
                "ethical_signal": "critical",
                "metacog_activity": "high",
            },
            "trend_analysis": {},
            "insights": ["Ethics under strain."],
        },
        {
            "overview": {
                "qualia_stability": "shifting",
                "ethical_signal": "moderate",
                "metacog_activity": "high",
            },
            "trend_analysis": {},
            "insights": ["Confidence steady.", "Metacognition rising."],
        },
    ]

    for report in reports:
        engine.update_chapter(report)

    summary = engine.summarize_identity()

    assert summary["core_themes"] == {
        "qualia": "stable",
        "ethics": "moderate",
        "metacognition": "high",
    }
    assert summary["recurring_insights"] == [
        "Confidence steady.",
        "Ethics under strain.",
        "Metacognition rising.",
    ]
    assert summary["chapter_count"] == 3


def test_insight_truncation_to_top_three():
    engine = SelfNarrativeEngine()
    report = {
        "overview": {"qualia_stability": "stable", "ethical_signal": "low", "metacog_activity": "low"},
        "trend_analysis": {},
        "insights": ["a", "b", "c", "d", "e"],
    }

    engine.update_chapter(report)
    chapter = engine.get_chapters()[0]

    assert chapter["key_insights"] == ["a", "b", "c"]


def test_chapter_isolation_from_mutation():
    engine = SelfNarrativeEngine()
    engine.update_chapter(
        {
            "overview": {"qualia_stability": "stable", "ethical_signal": "low", "metacog_activity": "low"},
            "trend_analysis": {"confidence": "stable"},
            "insights": ["Stable."],
        }
    )

    chapters = engine.get_chapters()
    chapters[0]["qualia_theme"] = "volatile"

    refreshed = engine.get_chapters()
    assert refreshed[0]["qualia_theme"] == "stable"
