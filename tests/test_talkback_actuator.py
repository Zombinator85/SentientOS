from pathlib import Path

import api.actuator as actuator


class DummyTalkback:
    def __init__(self, rtsp_url=None, ffmpeg_path=None) -> None:
        self.rtsp_url = rtsp_url or "rtsp://camera"
        self.ffmpeg_path = ffmpeg_path
        self.messages: list[str] = []

    def speak(self, text: str, voice=None) -> Path:
        self.messages.append(text)
        return Path("/tmp/fake.wav")


def test_talkback_actuator(monkeypatch):
    dummy = DummyTalkback()
    def factory(rtsp_url=None, ffmpeg_path=None):
        dummy.rtsp_url = rtsp_url or dummy.rtsp_url
        dummy.ffmpeg_path = ffmpeg_path
        return dummy

    monkeypatch.setattr(actuator, "CameraTalkback", factory)
    talkback = actuator.TalkbackActuator()
    result = talkback.execute({"message": "Stay calm", "url": "rtsp://foo"})
    assert result["ok"]
    assert result["target"] == "rtsp://foo"
    assert dummy.messages == ["Stay calm"]
