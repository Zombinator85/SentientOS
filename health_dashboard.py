from logging_config import get_log_path
import json
import os
from pathlib import Path
from flask_stub import Flask, jsonify, render_template_string
import memory_manager as mm
import orchestrator
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

app = Flask(__name__)

STATUS_TEMPLATE = """
<!doctype html>
<title>System Health</title>
<pre id="status">loading...</pre>
<script>
async function poll(){
  let r = await fetch('/status');
  let d = await r.json();
  document.getElementById('status').textContent = JSON.stringify(d, null, 2);
}
setInterval(poll, 5000);
window.onload=poll;
</script>
"""


@app.route('/')
def index():
    return render_template_string(STATUS_TEMPLATE)


def _last_heartbeat() -> str:
    hb_path = Path("cathedral_heartbeat.log")
    if not hb_path.exists():
        return "unknown"
    try:
        ts = hb_path.stat().st_mtime
        return str(ts)
    except Exception:
        return "unknown"


@app.route('/status')
def status():
    state = orchestrator.Orchestrator().status()
    memory_files = len(list(mm.RAW_PATH.glob('*.json')))
    token_spend = 0.0
    token_file = get_log_path("token_usage.json")
    if token_file.exists():
        try:
            token_spend = sum(json.loads(l).get('tokens', 0) for l in token_file.read_text().splitlines())
        except Exception:
            pass
    return jsonify({
        'relay_running': state.get('running'),
        'last_run': state.get('last_run'),
        'memory_fragments': memory_files,
        'token_spend': token_spend,
        'last_heartbeat': _last_heartbeat(),
    })


if __name__ == '__main__':  # pragma: no cover - manual
    require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    app.run(debug=True)
