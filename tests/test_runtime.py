from __future__ import annotations

import threading
from pathlib import Path

from harness.runtime import RuntimeContext, WebInteractionHandler
from harness.state import HarnessState


def test_web_interaction_handler_text_input_roundtrip(tmp_path: Path) -> None:
    state_path = tmp_path / ".harness" / "state.json"
    state = HarnessState.load(state_path)
    runtime = RuntimeContext(
        state=state,
        state_path=state_path,
        log_path=tmp_path / ".harness" / "logs" / "run.log",
    )
    handler = WebInteractionHandler(runtime)
    runtime.attach_interaction(handler)

    result: dict[str, str] = {}

    def worker() -> None:
        result["value"] = handler.text_input(
            stage="plan",
            action_type="idea_input",
            prompt="아이디어를 입력하세요",
        )

    thread = threading.Thread(target=worker)
    thread.start()

    while state.pending_action is None:
        pass

    assert state.run_status == "waiting_input"
    assert state.pending_action["type"] == "idea_input"

    handler.submit({"text": "웹 콘솔 추가"})
    thread.join(timeout=2)

    assert result["value"] == "웹 콘솔 추가"
    assert state.pending_action is None

