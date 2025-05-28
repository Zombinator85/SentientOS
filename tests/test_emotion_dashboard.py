import json
from emotion_dashboard import load_log


def test_load_log(tmp_path):
    log = tmp_path / 'vision.jsonl'
    log.write_text(json.dumps({'faces': []}) + '\n')
    data = load_log(str(log))
    assert data and data[0]['faces'] == []
