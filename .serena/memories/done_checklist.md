# Done checklist
- Run lint (`ruff check .`) on touched Python code.
- Run type checks (`mypy harness`) for impacted modules when feasible.
- Run relevant tests; currently there is no `tests/` directory, so add/execute tests as part of new features.
- For workflow changes, validate `harness run` / `harness status` behavior and persistence in `.harness/state.json`.
- For Jira-related changes, verify config loading and failure handling without exposing secrets.