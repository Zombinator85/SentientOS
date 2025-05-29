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

Reflex Manager
reflex_manager.py:
Runs reflex routines from timers, file changes, or on-demand triggers using the actuator.

Panic flag halts all actions.

Rules support interval, file_change, or on_demand triggers.

Example:

bash
Copy
Edit
python reflex_manager.py reflex.yml
Ctrl+C stops all rules.

Self-Reflection & Healing
self_reflection.py:
Monitors events and action logs, generating critiques and automatic self-healing patches.

Run the reflection manager periodically to critique and heal:

bash
Copy
Edit
python memory_cli.py self_reflect
All critiques, patches, and escalations are logged and queryable in the CLI/dashboard.

Presence Analytics
presence_analytics.py:
Computes presence trends and suggests optimizations.

Analyze emotion trends, routine health, patch/failure rates, and propose improvements.

Access analytics and suggestions via:

bash
Copy
Edit
python memory_cli.py analytics      # show presence analytics
python memory_cli.py trends         # emotion trends by day
python memory_cli.py suggest        # proposed optimizations
Memory Management, CLI, and Orchestration
Persistent storage:
memory_manager.py stores fragments with 64-D emotion vectors, indexed for vector search.

User profile & prompt assembly:
user_profile.py (key-value storage in profile.json),
prompt_assembler.py (builds model prompts from profile + memory).

Command-line usage (memory_cli.py):

Purge, summarize, playback, emotion timeline, patch management, agent cycles, orchestrator.

Example commands:

bash
Copy
Edit
python memory_cli.py purge --age 30
python memory_cli.py summarize
python memory_cli.py timeline
python memory_cli.py patches
python memory_cli.py orchestrator start --cycles 10
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
Every actuator action generates a reflection/critique.

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

Headless / Test Mode
--------------------
Set ``SENTIENTOS_HEADLESS=1`` to disable webcam, microphone, and network
dependencies. All modules will fall back to mocks and still log timestamped
events. This is useful for CI or development on machines without audio/vision
hardware.

Example:

```bash
export SENTIENTOS_HEADLESS=1
pytest
```

Policy, Gesture & Persona Engine
--------------------------------
`policy_engine.py` loads YAML or JSON policies at runtime to drive gestures and persona swaps. Policies define conditions on emotion vectors or tags and map them to actions. Use `python policy_engine.py policy show` to inspect active rules. Policies can be diffed, applied, or rolled back without restarting, and every action is audited.

Extensible Gesture & Persona Plug-ins
------------------------------------
Drop Python plug-ins in ``gp_plugins/`` to add new gestures or persona modules.
Each plug-in defines a ``register`` function that registers a ``BasePlugin``
subclass. Example plug-in:

```python
from plugin_framework import BasePlugin

class WaveHandPlugin(BasePlugin):
    plugin_type = "gesture"
    schema = {"speed": "float"}

    def execute(self, event):
        return {"gesture": "wave", "speed": event.get("speed", 1)}

    def simulate(self, event):
        return {"gesture": "wave", "speed": event.get("speed", 1), "explanation": "Simulated"}

def register(reg):
    reg("wave_hand", WaveHandPlugin())
```

List or test plug-ins:

```bash
python plugins_cli.py list
python plugins_cli.py test wave_hand
```
In headless mode plug-ins simulate actions but still log to the trust engine.
No secrets are present in this repo.
Copy .env.example to .env and fill in your credentials before running.

All components are modular, swappable, and extensible.
Presence, feedback, memory, reflection, analytics, and automation—no arbitrary limits.
The cathedral is ready.

