import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sentient_api


def test_status_endpoint():
    with sentient_api.app.test_client() as client:
        resp = client.get('/status')
        data = resp.get_json()
        assert {'uptime', 'pending_patches', 'cost_today'} <= data.keys()

