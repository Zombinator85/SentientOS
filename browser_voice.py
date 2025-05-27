from flask import Flask, request, send_file, jsonify
import tempfile
from mic_bridge import recognize_from_file
from tts_bridge import speak
from emotions import empty_emotion_vector

app = Flask(__name__)

@app.route('/')
def index():
    return '<h3>SentientOS Browser Voice Demo</h3>'

@app.route('/api/voice', methods=['POST'])
def voice_api():
    if 'audio' not in request.files:
        return jsonify({'error': 'no audio'}), 400
    f = request.files['audio']
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    f.save(tmp.name)
    result = recognize_from_file(tmp.name)
    text = result.get('message') or ''
    emotions = result.get('emotions') or empty_emotion_vector()
    audio_path = speak(text, emotions=emotions)
    return send_file(audio_path, mimetype='audio/mpeg')

if __name__ == '__main__':  # pragma: no cover - manual utility
    app.run(debug=True)
