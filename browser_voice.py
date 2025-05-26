import gradio as gr
from mic_bridge import recognize_from_file
from tts_bridge import speak


def converse(audio):
    if audio is None:
        return None, "", {}
    result = recognize_from_file(audio)
    text = result.get("message") or ""
    emotions = result.get("emotions") or {}
    reply_audio = speak(f"You said: {text}", emotions=emotions)
    return reply_audio, text, emotions


def main():
    with gr.Blocks() as demo:
        gr.Markdown("# SentientOS Voice Chat")
        in_audio = gr.Audio(source="microphone", type="filepath")
        out_audio = gr.Audio()
        transcript = gr.Textbox()
        emotions = gr.JSON()
        in_audio.change(converse, inputs=in_audio, outputs=[out_audio, transcript, emotions])
    demo.launch()


if __name__ == "__main__":  # pragma: no cover - manual utility
    main()
