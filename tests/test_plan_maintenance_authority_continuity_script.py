from scripts.maintenance_authority_continuity import main

def test_cli_help_is_bounded():
    try: main(["--help"])
    except SystemExit as exc: assert exc.code == 0
