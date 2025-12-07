import pytest

pytest.importorskip("pdfrw")

from agents.forms.ssa_disability_agent import SSADisabilityAgent


class DummyRelay:
    def __init__(self):
        self.screenshots = [b"shot1", b"shot2"]
        self.calls = []

    def goto(self, url: str):
        self.calls.append(("goto", url))
        return {"url": url}

    def type(self, selector: str, value: str):
        self.calls.append(("type", selector, value))
        return True

    def click(self, selector: str):
        self.calls.append(("click", selector))
        return True

    def screenshot(self):
        if self.screenshots:
            return self.screenshots.pop(0)
        return b"fallback"


def test_build_review_bundle_deterministic():
    agent = SSADisabilityAgent(profile={"first_name": "Test"})
    relay = DummyRelay()
    execution = agent.execute(relay, approval_flag=True)
    pdf_bytes = b"pdf"

    bundle = agent.build_review_bundle(execution_result=execution, pdf_bytes=pdf_bytes)
    bundle_dict = bundle.as_dict()

    assert bundle_dict["profile"] == {"first_name": "***"}
    assert bundle_dict["screenshots"] == ["<bytes>"] * len(bundle.screenshot_bytes)
    assert bundle_dict["execution_log"][0]["page"] == "intro"

    # Calling again should produce same screenshot placeholders length
    bundle_again = agent.build_review_bundle(execution_result=execution, pdf_bytes=pdf_bytes)
    assert len(bundle_again.screenshot_bytes) == len(bundle.screenshot_bytes)


def test_export_requires_approval():
    agent = SSADisabilityAgent(profile={"first_name": "Test"})
    bundle = agent.build_review_bundle(
        execution_result={"log": []}, pdf_bytes=b"", 
    )

    denied = agent.export_review_bundle(bundle, approved=False)
    assert denied == {"status": "approval_required"}

    approved = agent.export_review_bundle(bundle, approved=True)
    assert approved["status"] == "archive_ready"
    assert isinstance(approved["bytes"], (bytes, bytearray))
