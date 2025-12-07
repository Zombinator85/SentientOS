import inspect
from typing import Dict, List

import pytest

from sentientos.metacognition import MetaMonitor


def test_meta_monitor_importable():
    assert MetaMonitor is not None


def test_meta_monitor_methods_exist():
    monitor = MetaMonitor()
    for method in ("review_cycle", "get_recent_notes"):
        assert hasattr(monitor, method)


def test_meta_monitor_signatures():
    review_sig = inspect.signature(MetaMonitor.review_cycle)
    assert list(review_sig.parameters.keys()) == ["self", "state"]
    assert review_sig.parameters["state"].annotation == Dict[str, float]
    assert review_sig.return_annotation == List[Dict[str, str]]

    notes_sig = inspect.signature(MetaMonitor.get_recent_notes)
    assert list(notes_sig.parameters.keys()) == ["self", "limit"]
    assert notes_sig.parameters["limit"].default == 10
    assert notes_sig.parameters["limit"].annotation is int
    assert notes_sig.return_annotation == List[Dict[str, str]]


def test_meta_monitor_placeholders_raise():
    monitor = MetaMonitor()
    with pytest.raises(NotImplementedError):
        monitor.review_cycle({})

    with pytest.raises(NotImplementedError):
        monitor.get_recent_notes()
