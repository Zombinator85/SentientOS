import os
import json
import sys
import importlib

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def test_append_memory_emotion(tmp_path):
    os.environ['MEMORY_DIR'] = str(tmp_path)
    import memory_manager
    importlib.reload(memory_manager)
    fragment_id = memory_manager.append_memory("hello", tags=["t"], source="test", emotion="happy")
    data = json.loads((tmp_path / 'raw' / f"{fragment_id}.json").read_text())
    assert data['emotion'] == 'happy'
