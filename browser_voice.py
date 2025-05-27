from flask import Flask, request, jsonify
import base64
import tempfile
from mic_bridge import recognize_from_file
from tts_bridge import speak, set_voice_persona
from emotions import empty_emotion_vector

app = Flask(__name__)

@app.route('/')
def index():
    return '''<html><body>
    <h3>SentientOS Browser Voice Demo</h3>
    <input type="file" id="f" accept="audio/wav" />
    <button onclick="send()">Send</button>
    <select id="persona" onchange="setPersona()">
      <option value="default">Default</option>
      <option value="alt">Alt</option>
    </select>
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
    async function setPersona(){
        const p=document.getElementById('persona').value;
        await fetch('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona:p})});
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


@app.route('/api/persona', methods=['POST'])
def persona_api():
    data = request.get_json() or {}
    persona = data.get('persona', 'default')
    set_voice_persona(persona)
    return jsonify({'persona': persona})

if __name__ == '__main__':  # pragma: no cover - manual utility
    app.run(debug=True)
