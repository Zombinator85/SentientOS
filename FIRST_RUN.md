# First-Time Contributors

Welcome to SentientOS! This page helps you run the project locally with the healthy test suite.

## Clone and Setup

```bash
git clone <your-fork-url>
cd SentientOS
bash setup_env.sh
pip install -r requirements.txt
```

## Running Tests

Run only the passing tests with:

```bash
pytest -m "not env"  # legacy suites are skipped
```

## Need Help?

Reach out to the current Steward via the discussions board or open an issue labeled `support`.
