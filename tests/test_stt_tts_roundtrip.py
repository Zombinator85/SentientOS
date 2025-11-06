from stt_service import StreamingTranscriber
from tts_service import TtsStreamer


def test_streaming_transcriber_basic_flow():
    transcriber = StreamingTranscriber(vad_sensitivity=0.5)
    partial = transcriber.submit_audio(b"hello ")
    assert partial
    assert any(not event.final for event in partial)
    final = transcriber.submit_audio(b"world\n")
    utterances = [event.text for event in list(partial) + list(final) if event.final]
    assert utterances[-1] == "hello world"
    leftover = transcriber.flush()
    assert leftover == []


def test_tts_streamer_chunks():
    streamer = TtsStreamer(chunk_size=4)
    chunks = streamer.speak("hello")
    assert chunks
    assert b"hell" in chunks[0]
