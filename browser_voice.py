from flask import Flask, request, jsonify
import base64
import tempfile
from mic_bridge import recognize_from_file
from tts_bridge import speak
from emotions import empty_emotion_vector

app = Flask(__name__)

@app.route('/')
def index():
    return '''<html><body>
    <h3>SentientOS Browser Voice Demo</h3>
    <input type="file" id="f" accept="audio/wav" />
    <button onclick="send()">Send</button>
    <pre id="out"></pre>
    <script>
    async function send(){
        const file=document.getElementById('f').files[0];
        if(!file)return;
        const fd=new FormData();
        fd.append('audio',file);
        const res=await fetch('/api/voice',{method:'POST',body:fd});
        const j=await res.json();
        document.getElementById('out').textContent=JSON.stringify(j.emotions);
        const audio=new Audio('data:audio/mp3;base64,'+j.audio);audio.play();
    }
    </script></body></html>'''

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
    with open(audio_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return jsonify({'audio': b64, 'text': text, 'emotions': emotions})

if __name__ == '__main__':  # pragma: no cover - manual utility
    app.run(debug=True)
