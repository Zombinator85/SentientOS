from pathlib import Path
from subprocess import CompletedProcess

import logging

from sentientos.voice.asr import AsrConfig, WhisperAsr


def test_whisper_asr_transcribes_file(monkeypatch, tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")
    config = AsrConfig(
        whisper_binary_path=Path("/bin/whisper"),
        model_path=Path("/models/base.en.gguf"),
    )
    recorded_command = {}

    def fake_run(command, **kwargs):
        recorded_command["cmd"] = command
        return CompletedProcess(command, 0, stdout="hello world\n", stderr="")

    monkeypatch.setattr("sentientos.voice.asr.subprocess.run", fake_run)

    asr = WhisperAsr(config)
    transcript = asr.transcribe_file(audio_path)

    assert transcript == "hello world"
    assert recorded_command["cmd"][0] == str(config.whisper_binary_path)
    assert str(audio_path) in recorded_command["cmd"]


def test_whisper_asr_handles_missing_binary(monkeypatch, tmp_path, caplog):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")
    config = AsrConfig(
        whisper_binary_path=Path("/bin/missing"),
        model_path=Path("/models/base.en.gguf"),
    )

    def fake_run(command, **kwargs):
        raise FileNotFoundError("not found")

    monkeypatch.setattr("sentientos.voice.asr.subprocess.run", fake_run)

    asr = WhisperAsr(config)
    with caplog.at_level(logging.WARNING):
        transcript = asr.transcribe_file(audio_path)

    assert transcript == ""
    assert any("Whisper binary" in message for message in caplog.text.splitlines())


def test_whisper_asr_handles_non_zero_exit(monkeypatch, tmp_path, caplog):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")
    config = AsrConfig(
        whisper_binary_path=Path("/bin/whisper"),
        model_path=Path("/models/base.en.gguf"),
    )

    def fake_run(command, **kwargs):
        return CompletedProcess(command, 2, stdout="", stderr="failure")

    monkeypatch.setattr("sentientos.voice.asr.subprocess.run", fake_run)

    asr = WhisperAsr(config)
    with caplog.at_level(logging.WARNING):
        transcript = asr.transcribe_file(audio_path)

    assert transcript == ""
    assert any("exited" in message for message in caplog.text.splitlines())
