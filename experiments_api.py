"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from flask_stub import Flask, jsonify, request
import experiment_tracker as et


app = Flask(__name__)


@app.route('/experiments', methods=['GET', 'POST'])
def experiments() -> object:
    if request.method == 'POST':
        data = request.get_json() or {}
        exp_id = et.propose_experiment(
            data.get('description', ''),
            data.get('conditions', ''),
            data.get('expected', ''),
            proposer=data.get('user'),
            criteria=data.get('criteria'),
        )
        return jsonify({'id': exp_id})
    status = request.args.get('status')
    return jsonify(et.list_experiments(status))


@app.route('/experiments/vote', methods=['POST'])
def experiments_vote() -> object:
    data = request.get_json() or {}
    et.vote_experiment(data.get('id', ''), data.get('user', ''), not data.get('down'))
    return jsonify({'status': 'ok'})


@app.route('/experiments/comment', methods=['POST'])
def experiments_comment() -> object:
    data = request.get_json() or {}
    et.comment_experiment(data.get('id', ''), data.get('user', ''), data.get('text', ''))
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(port=5002)
