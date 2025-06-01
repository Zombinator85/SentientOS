import pathlib


def test_no_emotion_controls():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    files = [p for p in repo_root.rglob('*.py') if p.name != 'test_no_emotional_control.py']
    text = "\n".join(p.read_text('utf-8', errors='ignore') for p in files)
    forbidden = ['tone_template', 'tone slider', 'emotion preset', 'tone_preset']
    for phrase in forbidden:
        assert phrase not in text, f"Forbidden emotional control phrase found: {phrase}"

