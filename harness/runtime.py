"""
Runtime services for logging, events, and interactive input handling.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from harness.state import HarnessState


class StopRequestedError(RuntimeError):
    """Raised when the current run was stopped by the operator."""


class EventBus:
    """In-memory pub/sub for runtime events."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            for item in self._history:
                q.put(item)
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


class LogWriter:
    """Append-only log sink with a small in-memory tail."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tail: list[str] = []
        self._tail_limit = 200

    def write(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
            self._tail.append(line.rstrip("\n"))
            if len(self._tail) > self._tail_limit:
                self._tail = self._tail[-self._tail_limit :]

    def tail(self, limit: int = 100) -> list[str]:
        with self._lock:
            return self._tail[-limit:]


@dataclass
class PendingPrompt:
    request_id: str
    action_type: str
    stage: str
    prompt: str
    context: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class InteractionHandler:
    """Abstract interactive contract shared by CLI and web flows."""

    def text_input(
        self,
        *,
        stage: str,
        action_type: str,
        prompt: str,
        default: str = "",
        context: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        raise NotImplementedError

    def approval(
        self,
        *,
        stage: str,
        stage_label: str,
        summary: str,
        doc_path: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        raise NotImplementedError

    def decision(
        self,
        *,
        stage: str,
        question: str,
        context: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        raise NotImplementedError

    def confirm_retry(self, *, stage: str, stage_label: str) -> bool:
        raise NotImplementedError


class WebInteractionHandler(InteractionHandler):
    """Blocking bridge between background pipeline and web UI actions."""

    def __init__(self, runtime: "RuntimeContext") -> None:
        self.runtime = runtime
        self._pending: Optional[PendingPrompt] = None
        self._responses: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)

    def submit(self, payload: dict[str, Any]) -> None:
        try:
            while not self._responses.empty():
                self._responses.get_nowait()
        except queue.Empty:
            pass
        self.runtime.log(
            f"UI submitted action for {payload.get('stage') or 'unknown'}",
            event_type="ui_submit",
            stage=payload.get("stage"),
        )
        self._responses.put(payload)

    def _wait_for_response(self, prompt: PendingPrompt) -> dict[str, Any]:
        self._pending = prompt
        self.runtime.set_pending_action(
            {
                "request_id": prompt.request_id,
                "type": prompt.action_type,
                "stage": prompt.stage,
                "prompt": prompt.prompt,
                "context": prompt.context,
                "metadata": prompt.metadata,
            }
        )
        while True:
            self.runtime.raise_if_stopped()
            try:
                response = self._responses.get(timeout=0.2)
                if response.get("request_id") and response.get("request_id") != prompt.request_id:
                    self.runtime.log(
                        f"Ignoring stale UI action for {prompt.stage}",
                        event_type="ui_submit_stale",
                        stage=prompt.stage,
                    )
                    continue
                break
            except queue.Empty:
                continue
        self.runtime.log(
            f"Runtime received action for {prompt.stage}",
            event_type="ui_submit_ack",
            stage=prompt.stage,
        )
        self._pending = None
        self.runtime.clear_pending_action()
        return response or {}

    def text_input(
        self,
        *,
        stage: str,
        action_type: str,
        prompt: str,
        default: str = "",
        context: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        response = self._wait_for_response(
            PendingPrompt(
                request_id=uuid.uuid4().hex,
                action_type=action_type,
                stage=stage,
                prompt=prompt,
                context=context,
                metadata={"default": default, **(metadata or {})},
            )
        )
        return str(response.get("text") or default)

    def approval(
        self,
        *,
        stage: str,
        stage_label: str,
        summary: str,
        doc_path: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        response = self._wait_for_response(
            PendingPrompt(
                request_id=uuid.uuid4().hex,
                action_type="approval",
                stage=stage,
                prompt=summary,
                context=doc_path,
                metadata={"stage_label": stage_label, "doc_path": doc_path},
            )
        )
        return bool(response.get("approved")), response.get("notes")

    def decision(
        self,
        *,
        stage: str,
        question: str,
        context: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        response = self._wait_for_response(
            PendingPrompt(
                request_id=uuid.uuid4().hex,
                action_type="decision",
                stage=stage,
                prompt=question,
                context=context,
            )
        )
        return bool(response.get("proceed")), response.get("instruction")

    def confirm_retry(self, *, stage: str, stage_label: str) -> bool:
        response = self._wait_for_response(
            PendingPrompt(
                request_id=uuid.uuid4().hex,
                action_type="retry_decision",
                stage=stage,
                prompt=f"{stage_label} 실패 — implement부터 다시 실행할까요?",
                metadata={"stage_label": stage_label},
            )
        )
        return bool(response.get("retry"))


class RuntimeContext:
    """Run-scoped mutable services shared by pipeline, stages, and agents."""

    def __init__(
        self,
        *,
        state: HarnessState,
        state_path: Path,
        log_path: Path,
        run_id: Optional[str] = None,
        interaction: Optional[InteractionHandler] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.state = state
        self.state_path = state_path
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.event_bus = event_bus or EventBus()
        self.log_writer = LogWriter(log_path)
        self.interaction = interaction
        self._stop_event = threading.Event()
        self._process_lock = threading.Lock()
        self._current_process: Optional[subprocess.Popen[str]] = None

    def attach_interaction(self, interaction: InteractionHandler) -> None:
        self.interaction = interaction

    def raise_if_stopped(self) -> None:
        if self._stop_event.is_set():
            raise StopRequestedError("Run stopped by operator")

    def stop(self) -> None:
        self._stop_event.set()
        with self._process_lock:
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()
        self.log("Run stop requested")
        self.publish("run_stop_requested")

    def register_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            self._current_process = process

    def clear_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            if self._current_process is process:
                self._current_process = None

    def log(self, message: str, *, event_type: str = "log", stage: Optional[str] = None) -> None:
        line = message.rstrip()
        if stage:
            line = f"[{stage}] {line}"
        self.log_writer.write(line)
        self.publish(event_type, {"message": line, "stage": stage})
        self.state.active_log_path = str(self.log_writer.path)
        self.state.log_tail = self.log_writer.tail(100)
        self.state.save(self.state_path)

    def publish(self, event_type: str, payload: Optional[dict[str, Any]] = None) -> None:
        event = {"type": event_type, "run_id": self.run_id, **(payload or {})}
        self.event_bus.publish(event)

    def set_pending_action(self, action: dict[str, Any]) -> None:
        self.state.run_status = "waiting_input"
        self.state.pending_action = action
        self.state.save(self.state_path)
        summary = f"Waiting for {action.get('type')} input"
        if action.get("stage"):
            summary += f" on stage {action['stage']}"
        self.log(summary, event_type="waiting_input", stage=action.get("stage"))
        self.publish("stage_waiting_input", action)

    def clear_pending_action(self) -> None:
        if self.state.pending_action:
            self.log(
                f"Received input for {self.state.pending_action.get('type')}",
                event_type="input_received",
                stage=self.state.pending_action.get("stage"),
            )
        self.state.pending_action = None
        if self.state.run_status == "waiting_input":
            self.state.run_status = "running"
        self.state.save(self.state_path)

    def mark_run_started(self) -> None:
        self.state.run_id = self.run_id
        self.state.run_status = "running"
        self.state.active_log_path = str(self.log_writer.path)
        self.state.last_error = None
        self.state.save(self.state_path)
        self.publish("run_started")

    def mark_run_finished(self, status: str, error: Optional[str] = None) -> None:
        self.state.run_status = status
        self.state.last_error = error
        self.state.pending_action = None
        self.state.log_tail = self.log_writer.tail(100)
        self.state.save(self.state_path)
        self.publish("run_finished", {"status": status, "error": error})

    def sse_iter(self) -> Iterator[str]:
        subscriber = self.event_bus.subscribe()
        try:
            while True:
                event = subscriber.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == "run_finished" and event.get("run_id") == self.run_id:
                    break
        finally:
            self.event_bus.unsubscribe(subscriber)
