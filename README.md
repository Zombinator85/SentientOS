Multimodal Emotion Tracking & Feedback
multimodal_tracker.py
Fuses face detection, recognition, and facial emotion analysis with voice sentiment from the microphone. Each detected face is given a persistent ID and has a JSONL log written to logs/multimodal. The tracker works even when webcam or microphone libraries are missing.

Best free options:

Vision: MediaPipe or InsightFace

Facial emotion: FER or DeepFace

Voice sentiment: pyAudioAnalysis or openSMILE

Advanced audio: HuggingFace transformers (audio-classification pipeline)

To integrate a new model, simply replace FaceEmotionTracker.emotion or provide a custom mic_bridge.recognize_from_mic that returns an emotion vector. Swap components by subclassing MultiModalEmotionTracker or passing alternative backends. New modalities (text, gesture) can extend process and update timelines.

Emotional Feedback & Dashboard
Emotional feedback:
The Streamlit dashboard (emotion_dashboard.py) displays live, per-person emotion data and can trigger feedback rules defined in feedback.py.

Create a JSON file (e.g. feedback_rules.json):

json
Copy
Edit
[
  {"emotion": "Anger", "threshold": 0.7, "action": "print"}
]
Run the dashboard:

bash
Copy
Edit
streamlit run emotion_dashboard.py --server.port 8501
Use the sidebar to select a user, set refresh rate, and export or query past states.
When any face exceeds a threshold, the associated feedback action is executed (print, OSC, sound, etc).
Register new actions or embodiment targets via FeedbackManager.

Memory Management, CLI, and Orchestration
Persistent storage:
memory_manager.py stores fragments with 64-D emotion vectors, indexed for vector search.

Command-line usage via memory_cli.py:

Purge, summarize, playback, emotion timeline, patch management, agent cycles, orchestrator.

See full CLI details above for commands and patch event mapping.

Actuator, Reflections, and Plugins
Actuator CLI:
Sandboxed, whitelisted shell, HTTP, file, webhook, email actions—full CLI and /act endpoint.

Reflections & Critique:
Every actuator action generates a reflection/critique, query with memory_cli.py reflections.

Plugin discovery/reload:
Drop plugins in plugins/; reload live via CLI.

Log Tailing and Tests
Tail logs:

bash
Copy
Edit
python memory_tail.py
Use --file to tail a different log.

Run all tests:

bash
Copy
Edit
pytest
No secrets are present in this repo.
Copy .env.example to .env and fill in your credentials before running.