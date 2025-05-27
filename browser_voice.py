from flask import Flask, request, jsonify, send_file
from pathlib import Path
import tempfile

from mic_bridge import recognize_from_file
from tts_bridge import speak
from emotions import empty_emotion_vector

app = Flask(__name__)

@app.route("/")
def index():
    return (
        "<html><body>"
        "<h3>Browser Voice Demo</h3>"
        "<form method='post' action='/chat' enctype='multipart/form-data'>"
        "<input type='file' name='audio'/><input type='submit'/>"
        "</form>"
        "</body></html>"
    )

@app.route("/chat", methods=["POST"])
def chat():
    f = request.files['audio']
    temp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    f.save(temp.name)
    res = recognize_from_file(temp.name)
    text = res.get('message') or ''
    emotions = res.get('emotions') or empty_emotion_vector()
    reply_audio = speak(f"Echo: {text}", emotions=emotions)
    return jsonify({'text': text, 'audio': reply_audio})

if __name__ == '__main__':  # pragma: no cover - manual utility
    app.run(port=8080)
