from scripts.codex_finalize_landing import build_parser


def test_parser_has_phase_and_changed_file() -> None:
    p = build_parser()
    args = p.parse_args([
        "finalize",
        "--title",
        "t",
        "--intended-commit-title",
        "t",
        "--phase",
        "pre-commit",
        "--changed-file",
        "sentientos/codex_finalize_landing.py",
    ])
    assert args.cmd == "finalize"
    assert args.phase == "pre-commit"
    assert args.changed_file == ["sentientos/codex_finalize_landing.py"]
