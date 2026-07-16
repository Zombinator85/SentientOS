from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from sentientos.codex_landing_evidence_binding import classify_publication_result, create_body_binding, verify_body_binding

from typing import Any

def load(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('JSON artifact must be an object')
    return data

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    b=sub.add_parser('bind-body'); b.add_argument('--title', required=True); b.add_argument('--body-path', required=True); b.add_argument('--commit-binding-json', required=True); b.add_argument('--artifact', action='append', default=[]); b.add_argument('--output', required=True)
    v=sub.add_parser('verify-body'); v.add_argument('--title', required=True); v.add_argument('--body-path', required=True); v.add_argument('--binding-json', required=True); v.add_argument('--artifact', action='append', default=[]); v.add_argument('--summary', action='store_true')
    c=sub.add_parser('classify-publication'); c.add_argument('--publication-json', required=True); c.add_argument('--expected-json', required=True); c.add_argument('--summary', action='store_true')
    a=p.parse_args(argv)
    def artifacts(items: list[str]) -> dict[str, str]:
        return dict(item.split('=',1) for item in items)
    if a.cmd=='bind-body':
        side=create_body_binding(a.title, a.body_path, load(a.commit_binding_json), artifacts(a.artifact)).to_dict(); Path(a.output).write_text(json.dumps(side, indent=2, sort_keys=True), encoding='utf-8'); print(json.dumps({'status':'pr_body_binding_written','body_sha256':side['body_sha256']}, indent=2)); return 0
    if a.cmd=='verify-body':
        res=verify_body_binding(a.title, a.body_path, load(a.binding_json), artifacts(a.artifact)); print(json.dumps(res.to_dict() if not a.summary else {'status':res.status,'reasons':res.reasons,'proof':res.proof}, indent=2, sort_keys=True)); return 0 if res.status=='pr_body_binding_ready' else 1
    res=classify_publication_result(load(a.publication_json), load(a.expected_json)); print(json.dumps(res.to_dict() if not a.summary else {'status':res.status,'reasons':res.reasons,'proof':res.proof}, indent=2, sort_keys=True)); return 0 if not res.status.endswith('contradicted') else 1
if __name__=='__main__': raise SystemExit(main())
