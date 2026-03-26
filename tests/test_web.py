from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from harness.config import HarnessConfig
from harness.state import HarnessState, JiraIssue
from harness.web import create_app


def _write_project(tmp_path: Path) -> None:
    config = HarnessConfig()
    config.project.name = "demo"
    config.save(tmp_path / "harness.yml")
    state_path = tmp_path / config.paths.state
    HarnessState.load(state_path).save(state_path)


def test_current_run_endpoint_returns_state(tmp_path: Path) -> None:
    _write_project(tmp_path)
    client = TestClient(create_app(root=str(tmp_path)))

    response = client.get("/runs/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == "demo"
    assert payload["state"]["run_status"] == "pending"


def test_run_and_stage_input_routes_delegate_to_manager(tmp_path: Path, monkeypatch) -> None:
    _write_project(tmp_path)
    app = create_app(root=str(tmp_path))
    client = TestClient(app)
    manager = app.state.manager
    captured: dict[str, object] = {}

    class DummyRuntime:
        run_id = "run-123"

    monkeypatch.setattr(manager, "start_run", lambda **kwargs: DummyRuntime())
    monkeypatch.setattr(manager, "submit_action", lambda payload: captured.setdefault("payload", payload))

    run_response = client.post("/runs", json={"stage": "plan", "force": True})
    input_response = client.post("/stages/plan/input", json={"text": "refine"})

    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == "run-123"
    assert input_response.status_code == 200
    assert captured["payload"]["text"] == "refine"


def test_jira_create_from_tasks_uses_saved_breakdown(tmp_path: Path, monkeypatch) -> None:
    _write_project(tmp_path)
    app = create_app(root=str(tmp_path))
    client = TestClient(app)
    manager = app.state.manager
    config, state, state_path = manager.load_state()
    config.jira.url = "https://example.atlassian.net"
    config.jira.email = "dev@example.com"
    config.jira.api_token = "token"
    config.jira.project_key = "DEMO"
    config.save(manager.config_path)
    state.get_stage("tasks").metadata["breakdown"] = {
        "epics": [{"summary": "Epic 1", "description": "", "stories": []}]
    }
    state.save(state_path)

    monkeypatch.setattr("harness.web.JiraClient.ping", lambda self: True)
    monkeypatch.setattr(
        "harness.web.JiraClient.create_hierarchy",
        lambda self, breakdown: [
            JiraIssue(key="DEMO-1", summary="Epic 1", issue_type="Epic", url="https://example/DEMO-1")
        ],
    )

    response = client.post("/jira/create-from-tasks", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"][0]["key"] == "DEMO-1"
