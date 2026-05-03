from __future__ import annotations

from sentientos.perception_api import (
    build_feedback_observation,
    build_perception_event,
    normalize_audio_observation,
    normalize_multimodal_observation,
    normalize_screen_observation,
    normalize_vision_observation,
)


def test_perception_api_shapes_are_non_authoritative() -> None:
    screen = normalize_screen_observation(text="hi", ocr_confidence=0.8, width=10, height=20, timestamp=1.0)
    audio = normalize_audio_observation(message="hello", source="mic", audio_file=None, emotion_features={"joy": 0.4}, timestamp=2.0)
    vision = normalize_vision_observation(faces=[{"id": 1, "emotions": {"joy": 0.9}}], timestamp=3.0)
    multi = normalize_multimodal_observation(timestamp=4.0, vision=vision, voice=audio, scene={"summary": "desk"}, screen=screen)
    feedback = build_feedback_observation(user=1, emotion="joy", value=0.9, action="cue", timestamp=5.0)

    event = build_perception_event("multimodal", multi, source="legacy", raw_retention=False)
    assert event["authority"] == "none"
    assert event["telemetry_only"] is True
    assert event["raw_retention"] is False
    assert feedback["action"] == "cue"


def test_legacy_modules_keep_public_symbols() -> None:
    from feedback import FeedbackManager, FeedbackRule
    from mic_bridge import recognize_from_file, recognize_from_mic
    from multimodal_tracker import MultiModalEmotionTracker
    from screen_awareness import ScreenAwareness
    from vision_tracker import FaceEmotionTracker

    assert FeedbackManager is not None and FeedbackRule is not None
    assert callable(recognize_from_mic) and callable(recognize_from_file)
    assert MultiModalEmotionTracker is not None
    assert ScreenAwareness is not None
    assert FaceEmotionTracker is not None
