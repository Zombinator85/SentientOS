#!/usr/bin/env python3
import argparse, hashlib, json, os, sys
from pathlib import Path

def bd(p): return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    if len(sys.argv)>1 and sys.argv[1]=='version': print('fake-pr 1'); return 0
    mode=os.environ.get('FAKE_PR_MODE','ok')
    if mode=='auth': return 3
    if mode=='malformed': print('{'); return 0
    root=Path(os.environ.get('FAKE_PR_ROOT', os.getcwd()))/'prs.json'; prs=json.loads(root.read_text()) if root.exists() else []
    cmd=sys.argv[1]
    ap=argparse.ArgumentParser(); ap.add_argument('--repo'); ap.add_argument('--head'); ap.add_argument('--base'); ap.add_argument('--title'); ap.add_argument('--body-file')
    ns=ap.parse_args(sys.argv[2:])
    if cmd=='pr-list': print(json.dumps([p for p in prs if p['repository']==ns.repo and p['headRefName']==ns.head and p['baseRefName']==ns.base])); return 0
    if cmd=='pr-create':
        pr={'number':len(prs)+1,'url':'fake://pr/'+str(len(prs)+1),'state':'OPEN','repository':ns.repo,'headRefName':ns.head,'headRefOid':os.environ.get('FAKE_HEAD_SHA',''),'baseRefName':ns.base,'title':ns.title,'bodyDigest':bd(ns.body_file)}
        prs.append(pr); root.write_text(json.dumps(prs,sort_keys=True)); print(json.dumps(pr)); return 0
    if cmd=='pr-view': print(json.dumps(prs[-1] if prs else {})); return 0
    return 2
if __name__=='__main__': raise SystemExit(main())
