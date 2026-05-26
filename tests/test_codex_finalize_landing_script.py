from scripts.codex_finalize_landing import build_parser

def test_parser_has_finalize():
    p=build_parser()
    args=p.parse_args(['finalize','--title','t','--intended-commit-title','t'])
    assert args.cmd=='finalize'
