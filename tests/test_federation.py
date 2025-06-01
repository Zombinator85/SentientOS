import importlib
import love_treasury as lt
import treasury_federation as tf
import pytest


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVE_SUBMISSIONS_LOG", str(tmp_path / "sub.jsonl"))
    monkeypatch.setenv("LOVE_REVIEW_LOG", str(tmp_path / "rev.jsonl"))
    monkeypatch.setenv("LOVE_TREASURY_LOG", str(tmp_path / "tre.jsonl"))
    monkeypatch.setenv("LOVE_FEDERATED_LOG", str(tmp_path / "fed.jsonl"))
    importlib.reload(lt)
    importlib.reload(tf)


def test_import_payload(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    lid = lt.submit_log("Loc", ["a"], "now", "demo", "text", user="a")
    lt.review_log(lid, "cur", "affirm")
    payload = lt.list_treasury()
    imported = tf.import_payload(payload, origin="remote")
    assert imported and imported[0] == lid
    fed = lt.list_federated()
    assert fed and fed[0]["id"] == lid

