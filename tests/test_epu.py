import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from epu import EPU, EPU_EMOTIONS


def test_emotion_list_len():
    assert len(EPU_EMOTIONS) == 64


def test_fusion_prefers_highest_score():
    e = EPU()
    e.update_audio("happy", 0.6)
    e.update_video("sad", 0.3)
    assert e.get_epu_state()["epu_fused"]["label"] == "happy"


def test_missing_channels():
    e = EPU()
    e.update_text("neutral", 0.5)
    state = e.get_epu_state()
    assert state["epu_fused"]["label"] == "neutral"
