# Style and conventions
- Language: Python with type hints throughout; modules use concise docstrings and Korean user-facing strings.
- Models/config: Pydantic BaseModel classes for config and state.
- CLI/UX: Typer commands with Rich output and prompt-driven confirmations.
- Architecture: stage classes inherit `BaseStage`; agent wrappers inherit `BaseAgent`; pipeline sequencing lives centrally in `Pipeline`.
- Persistence: Markdown docs under `docs/`, YAML config in `harness.yml`, JSON state in `.harness/state.json`.