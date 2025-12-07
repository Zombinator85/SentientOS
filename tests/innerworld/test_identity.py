import inspect
from typing import Dict, List

import pytest

from sentientos.identity import IdentityManager


def test_identity_manager_importable():
    assert IdentityManager is not None


def test_identity_manager_methods_exist():
    manager = IdentityManager()
    for method in (
        "log_event",
        "get_events",
        "summarize",
        "get_self_concept",
        "update_self_concept",
    ):
        assert hasattr(manager, method)


def test_identity_manager_signatures():
    log_sig = inspect.signature(IdentityManager.log_event)
    assert list(log_sig.parameters.keys()) == ["self", "event_type", "description"]
    assert log_sig.parameters["event_type"].annotation is str
    assert log_sig.parameters["description"].annotation is str

    events_sig = inspect.signature(IdentityManager.get_events)
    assert list(events_sig.parameters.keys()) == ["self", "limit"]
    assert events_sig.parameters["limit"].default == 50
    assert events_sig.parameters["limit"].annotation is int
    assert events_sig.return_annotation == List[Dict[str, str]]

    summarize_sig = inspect.signature(IdentityManager.summarize)
    assert list(summarize_sig.parameters.keys()) == ["self"]
    assert summarize_sig.return_annotation is str

    self_concept_sig = inspect.signature(IdentityManager.get_self_concept)
    assert list(self_concept_sig.parameters.keys()) == ["self"]
    assert self_concept_sig.return_annotation == Dict[str, str]

    update_sig = inspect.signature(IdentityManager.update_self_concept)
    assert list(update_sig.parameters.keys()) == ["self", "key", "value"]
    assert update_sig.parameters["key"].annotation is str
    assert update_sig.parameters["value"].annotation is str


def test_identity_manager_placeholders_raise():
    manager = IdentityManager()
    with pytest.raises(NotImplementedError):
        manager.log_event("test", "description")

    with pytest.raises(NotImplementedError):
        manager.get_events()

    with pytest.raises(NotImplementedError):
        manager.summarize()

    with pytest.raises(NotImplementedError):
        manager.get_self_concept()

    with pytest.raises(NotImplementedError):
        manager.update_self_concept("trait", "value")
