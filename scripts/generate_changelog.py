import subprocess


def main() -> None:
    log = subprocess.check_output([
        "git",
        "log",
        "--pretty=format:* %s (%h)",
        "v0.4.0..HEAD",
    ], text=True)
    print(log)


if __name__ == "__main__":
    main()
