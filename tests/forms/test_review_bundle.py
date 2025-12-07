from agents.forms.review_bundle import SSAReviewBundle, redact_dict, redact_log


def test_redact_dict_masks_strings_only():
    profile = {"name": "Alice", "age": 30, "nested": {"city": "Somewhere"}, "list": ["one", {"two": "value"}]}
    redacted = redact_dict(profile)

    assert redacted == {"name": "***", "age": 30, "nested": {"city": "***"}, "list": ["***", {"two": "***"}]}


def test_redact_log_masks_sensitive_fields_and_preserves_page():
    log = [
        {"page": "intro", "action": "navigate", "result": {"status": "navigated", "selector": "#link", "value": "abc"}},
        {"page": "intro", "action": "fill", "selector": "#field", "value": "secret", "result": {"selector": "#field"}},
        {"page": "summary", "result": {"status": "screenshot", "bytes": b"raw"}},
    ]

    redacted = redact_log(log)

    assert redacted[0]["page"] == "intro"
    assert redacted[0]["result"]["selector"] == "***"
    assert redacted[0]["result"]["value"] == "***"
    assert redacted[1]["selector"] == "***"
    assert redacted[1]["value"] == "***"
    assert redacted[2]["result"]["bytes"] == "***"


def test_review_bundle_dict_output_and_archive_gate():
    execution_log = [
        {"page": "intro", "action": "fill", "selector": "#field", "value": "secret", "result": {"status": "filled"}},
        {"page": "summary", "action": "screenshot", "result": {"status": "screenshot", "bytes": b"img"}},
    ]
    pdf_bytes = b"pdf"
    screenshots = [b"img"]
    profile = {"first_name": "Ada"}

    bundle = SSAReviewBundle(execution_log=execution_log, screenshot_bytes=screenshots, pdf_bytes=pdf_bytes, profile=profile)
    as_dict = bundle.as_dict()

    assert as_dict["execution_log"][0]["selector"] == "***"
    assert as_dict["execution_log"][0]["value"] == "***"
    assert as_dict["screenshots"] == ["<bytes>"]
    assert as_dict["prefilled_pdf"] == "<bytes>"
    assert as_dict["profile"] == {"first_name": "***"}

    denied = bundle.as_archive(approved=False)
    assert denied == {"status": "approval_required"}

    approved = bundle.as_archive(approved=True)
    assert approved["status"] == "archive_ready"
    assert isinstance(approved["bytes"], (bytes, bytearray))

    # Determinism: repeated call yields identical bytes
    approved_again = bundle.as_archive(approved=True)
    assert approved_again["bytes"] == approved["bytes"]
