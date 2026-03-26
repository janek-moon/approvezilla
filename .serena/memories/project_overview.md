# agent-harness overview
- Purpose: Python-based AI agent workflow harness orchestrating 8 stages from planning to closeout for software delivery.
- Stack: Python 3.10+, Typer CLI, Rich terminal UI, Pydantic v2 config/state models, PyYAML, Requests, python-dotenv.
- Structure: `harness/cli.py` is the CLI entrypoint; `harness/pipeline.py` orchestrates stages; `harness/stages/` contains stage implementations; `harness/agents/` wraps Claude/Codex/CodeRabbit CLIs; `harness/jira_client.py` handles Jira REST; `harness/state.py` stores pipeline stage state in `.harness/state.json`; docs are persisted under `docs/`.
- Current UX: terminal-driven only, with interactive prompts for approvals and some stage inputs.
- Jira: configured via `harness.yml` and/or `JIRA_*` env vars, used primarily by `tasks` stage to create hierarchy issues.