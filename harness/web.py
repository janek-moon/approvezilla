"""
FastAPI web console for local harness operation.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

import markdown as md
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from harness.config import HarnessConfig
from harness.jira_client import JiraClient
from harness.pipeline import Pipeline
from harness.runtime import RuntimeContext, WebInteractionHandler
from harness.state import HarnessState


class HarnessWebManager:
    def __init__(self, project_root: Path, config_file: str) -> None:
        self.project_root = project_root
        self.config_file = config_file
        self._lock = threading.Lock()
        self._runtime: Optional[RuntimeContext] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def config_path(self) -> Path:
        return self.project_root / self.config_file

    def load_config(self) -> HarnessConfig:
        return HarnessConfig.load(self.config_path)

    def save_config(self, config: HarnessConfig) -> None:
        config.save(self.config_path)

    def load_state(self) -> tuple[HarnessConfig, HarnessState, Path]:
        config = self.load_config()
        state_path = self.project_root / config.paths.state
        state = HarnessState.load(state_path)
        state.project = config.project.name
        return config, state, state_path

    def current_runtime(self) -> Optional[RuntimeContext]:
        with self._lock:
            if self._thread and not self._thread.is_alive():
                self._thread = None
                self._runtime = None
            return self._runtime

    def start_run(
        self,
        *,
        stage: Optional[str] = None,
        from_stage: Optional[str] = None,
        to_stage: Optional[str] = None,
        force: bool = False,
    ) -> RuntimeContext:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A run is already active")

            config, state, state_path = self.load_state()
            if force:
                from harness.cli import _resolve_stages

                for stage_name in _resolve_stages(stage, from_stage, to_stage):
                    state.get_stage(stage_name).reset_to_pending()
                state.save(state_path)

            log_dir = self.project_root / config.paths.logs
            runtime = RuntimeContext(
                state=state,
                state_path=state_path,
                log_path=log_dir / "web-current.log",
            )
            interaction = WebInteractionHandler(runtime)
            runtime.attach_interaction(interaction)
            pipeline = Pipeline(config, state, self.project_root, runtime=runtime)

            def runner() -> None:
                try:
                    pipeline.run(from_stage=from_stage, to_stage=to_stage, only_stage=stage)
                except Exception as exc:
                    runtime.log(f"Run failed: {exc}", event_type="run_error")
                    if state.run_status != "failed":
                        runtime.mark_run_finished("failed", str(exc))

            thread = threading.Thread(target=runner, daemon=True)
            self._runtime = runtime
            self._thread = thread
            thread.start()
            return runtime

    def stop_run(self, run_id: str) -> None:
        runtime = self.current_runtime()
        if not runtime or runtime.run_id != run_id:
            raise RuntimeError("No matching active run")
        runtime.stop()

    def submit_action(self, payload: dict[str, Any]) -> None:
        runtime = self.current_runtime()
        if not runtime or not isinstance(runtime.interaction, WebInteractionHandler):
            config, state, state_path = self.load_state()
            if state.pending_action is not None:
                state.pending_action = None
                if state.run_status == "waiting_input":
                    state.run_status = "failed"
                state.save(state_path)
            raise RuntimeError("No active interactive run")
        runtime.interaction.submit(payload)


def create_app(root: str = ".", config_file: str = "harness.yml") -> FastAPI:
    project_root = Path(root).resolve()
    asset_root = Path(__file__).resolve().parent
    app = FastAPI(title="agent-harness web console")
    templates = Jinja2Templates(directory=str(asset_root / "templates"))
    app.mount("/static", StaticFiles(directory=str(asset_root / "static")), name="static")
    manager = HarnessWebManager(project_root, config_file)
    app.state.manager = manager
    app.state.templates = templates

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        config, state, _ = manager.load_state()
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "config": config,
                "state": state,
            },
        )

    @app.get("/runs/current")
    async def current_run() -> JSONResponse:
        config, state, _ = manager.load_state()
        return JSONResponse(
            {
                "project": config.project.name,
                "state": state.model_dump(),
                "stages": {name: st.model_dump() for name, st in state.stages.items()},
            }
        )

    @app.post("/runs")
    async def start_run(request: Request) -> JSONResponse:
        payload = await request.json()
        runtime = manager.start_run(
            stage=payload.get("stage"),
            from_stage=payload.get("from_stage"),
            to_stage=payload.get("to_stage"),
            force=bool(payload.get("force")),
        )
        return JSONResponse({"run_id": runtime.run_id})

    @app.post("/runs/{run_id}/stop")
    async def stop_run(run_id: str) -> JSONResponse:
        manager.stop_run(run_id)
        return JSONResponse({"ok": True})

    @app.get("/runs/{run_id}/events")
    async def stream_events(run_id: str) -> StreamingResponse:
        runtime = manager.current_runtime()
        if not runtime or runtime.run_id != run_id:
            raise HTTPException(status_code=404, detail="Run not found")
        return StreamingResponse(runtime.sse_iter(), media_type="text/event-stream")

    @app.post("/stages/{stage}/approve")
    async def approve_stage(stage: str, request: Request) -> JSONResponse:
        payload = await request.json()
        try:
            manager.submit_action(
                {
                    "approved": True,
                    "notes": payload.get("notes"),
                    "stage": stage,
                    "request_id": payload.get("request_id"),
                }
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse({"ok": True})

    @app.post("/stages/{stage}/reject")
    async def reject_stage(stage: str, request: Request) -> JSONResponse:
        payload = await request.json()
        try:
            manager.submit_action(
                {
                    "approved": False,
                    "notes": payload.get("reason"),
                    "stage": stage,
                    "request_id": payload.get("request_id"),
                }
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse({"ok": True})

    @app.post("/stages/{stage}/input")
    async def stage_input(stage: str, request: Request) -> JSONResponse:
        payload = await request.json()
        try:
            manager.submit_action(
                {
                    "stage": stage,
                    "text": payload.get("text"),
                    "proceed": payload.get("proceed"),
                    "instruction": payload.get("instruction"),
                    "retry": payload.get("retry"),
                    "request_id": payload.get("request_id"),
                }
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse({"ok": True})

    @app.get("/config")
    async def get_config() -> JSONResponse:
        return JSONResponse(manager.load_config().model_dump())

    @app.post("/config")
    async def update_config(request: Request) -> JSONResponse:
        payload = await request.json()
        config = HarnessConfig.model_validate(payload)
        manager.save_config(config)
        return JSONResponse({"ok": True})

    @app.post("/idea")
    async def update_idea(request: Request) -> JSONResponse:
        payload = await request.json()
        _, state, state_path = manager.load_state()
        state.idea = payload.get("idea") or None
        state.save(state_path)
        return JSONResponse({"ok": True, "idea": state.idea})

    @app.post("/jira/test")
    async def jira_test(request: Request) -> JSONResponse:
        payload = await request.json()
        if not payload.get("enabled", False):
            return JSONResponse({"ok": False, "message": "Jira is disabled"})
        client = JiraClient(
            url=payload.get("url"),
            email=payload.get("email"),
            api_token=payload.get("api_token"),
            project_key=payload.get("project_key"),
        )
        return JSONResponse({"ok": client.ping()})

    @app.post("/jira/create-from-tasks")
    async def jira_create_from_tasks() -> JSONResponse:
        config, state, state_path = manager.load_state()
        if not config.jira.enabled:
            raise HTTPException(status_code=400, detail="Jira is disabled")
        breakdown = state.get_stage("tasks").metadata.get("breakdown")
        if not breakdown:
            raise HTTPException(status_code=400, detail="No task breakdown available")
        client = JiraClient(
            url=config.jira.url,
            email=config.jira.email,
            api_token=config.jira.api_token,
            project_key=config.jira.project_key,
        )
        if not client.ping():
            raise HTTPException(status_code=400, detail="Jira connection failed")
        created = client.create_hierarchy(breakdown)
        state.get_stage("tasks").jira_issues = created
        state.save(state_path)
        return JSONResponse({"created": [issue.model_dump() for issue in created]})

    @app.get("/docs/{stage}")
    async def stage_doc(stage: str) -> JSONResponse:
        config, state, _ = manager.load_state()
        stage_state = state.get_stage(stage)
        content = stage_state.output or ""
        source = "output"
        if stage_state.doc_path:
            doc_path = Path(stage_state.doc_path)
            if not doc_path.is_absolute():
                doc_path = project_root / doc_path
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8")
                source = str(doc_path)
        rendered = md.markdown(
            content,
            extensions=[
                "tables",
                "fenced_code",
                "sane_lists",
                "nl2br",
            ],
        )
        return JSONResponse(
            {
                "stage": stage,
                "content": content,
                "html": rendered,
                "source": source,
            }
        )

    return app
