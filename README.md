Multimodal Emotion Tracking & Feedback
multimodal_tracker.py
Fuses face detection, recognition, and facial emotion analysis with voice sentiment from the microphone.

Each detected face is given a persistent ID and has a JSONL log written to logs/multimodal.

Tracker works even if webcam or microphone libraries are missing.

Best free options:

Vision: MediaPipe or InsightFace

Facial emotion: FER or DeepFace

Voice sentiment: pyAudioAnalysis or openSMILE

Advanced audio: HuggingFace transformers (audio-classification pipeline)

To integrate a new model, replace FaceEmotionTracker.emotion or provide a custom mic_bridge.recognize_from_mic that returns an emotion vector. Swap components by subclassing MultiModalEmotionTracker or passing alternative backends. New modalities (text, gesture) can extend process and update timelines.

Emotional Feedback & Dashboard
Emotional feedback
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

Reflex Manager
reflex_manager.py:

Runs reflex routines from timers, file changes, or on-demand triggers using the actuator.

Panic flag halts all actions.

Rules support interval, file_change, or on_demand triggers and use the actuator to perform actions.

Example:

bash
Copy
Edit
python reflex_manager.py reflex.yml
Ctrl+C stops all rules.

Memory Management, CLI, and Orchestration
Persistent storage:
memory_manager.py stores fragments with 64-D emotion vectors, indexed for vector search.

User profile and prompt assembly:
user_profile.py (stores persistent key-values in profile.json);
prompt_assembler.py (combines profile and memory for rich model prompts).

Command-line usage via memory_cli.py:

Purge, summarize, playback, emotion timeline, patch management, agent cycles, orchestrator.

Full CLI:

bash
Copy
Edit
python memory_cli.py purge --age 30       # delete old fragments
python memory_cli.py summarize            # build daily summaries
python memory_cli.py timeline             # view emotion timeline
python memory_cli.py patches              # manage patch proposals
python memory_cli.py orchestrator start   # run orchestrator cycles
Patch event mapping:

apply_patch → self_patch

approve_patch → patch_approved

reject_patch → patch_rejected

rollback_patch → patch_rolled_back

Actuator, Reflections, and Plugins
Actuator CLI (api/actuator.py):

Sandboxed, whitelisted shell, HTTP, file, webhook, email actions—full CLI and /act endpoint.

Example:

bash
Copy
Edit
python api/actuator.py shell "ls -l"
python api/actuator.py write --file out.txt --text "hello"
Reflections & Critique:

Every actuator action generates a reflection/critique, query with memory_cli.py reflections.

Example:

bash
Copy
Edit
python memory_cli.py reflections --last 3
python memory_cli.py reflections --failures --json
Plugin discovery/reload:

Drop plugins in plugins/; reload live via CLI:

bash
Copy
Edit
python api/actuator.py plugins --reload
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

All components are modular, swappable, and extensible.
Presence, feedback, memory, and automation—no arbitrary limits.
Cathedral is ready.

