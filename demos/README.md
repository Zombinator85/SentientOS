# Demo Gallery

The demo gallery provides deterministic end-to-end experiment runs that can be
executed without hardware or external APIs. Each demo loads a JSON
specification, prepares any required experiments with the mock adapter, creates
an experiment chain, and executes it through the standard runner and logging
stack.

## Available demos

Run the commands from the repository root:

```bash
python experiment_cli.py demo-list
python experiment_cli.py demo-run demo_simple_success
```

### demo_simple_success

Single-step experiment that uses the mock adapter to measure temperature and
validates the DSL criteria `temp_c >= 20.0`. Demonstrates a clean, successful
run with full logging.

### demo_chain_branch

Three-step branching chain. The first experiment checks the mock temperature and
continues to either the success validation or a recovery step based on the
criteria outcome. Useful for exercising success/failure routing in the runner.

## Notes

* All demos run against the deterministic mock adapter.
* Chain execution logs are written to the standard experiment chain log path
  (`EXPERIMENT_CHAIN_LOG`).
* Demos can be executed repeatedly; the resulting experiment identifiers and
  outcomes remain stable across runs.
