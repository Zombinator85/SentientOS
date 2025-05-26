import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import emotion_utils as eu


def test_vad_to_epu_mapping():
    if eu.np is None:
        pytest.skip("numpy not available")
    vec = eu.vad_to_epu(0.5, 0.8, 0.7)
    assert vec["Joy"] > 0
    assert vec["Enthusiasm"] > 0
    assert vec["Confident"] > 0

