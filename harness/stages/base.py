"""
BaseStage — 모든 Stage의 추상 기반 클래스
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.rule import Rule

if TYPE_CHECKING:
    from harness.config import HarnessConfig
    from harness.runtime import RuntimeContext
    from harness.state import HarnessState

console = Console()


class BaseStage(ABC):
    """단계 실행의 공통 인터페이스."""

    stage_name:  str = ""
    stage_label: str = ""

    def __init__(
        self,
        config: "HarnessConfig",
        state: "HarnessState",
        project_root: Path,
        runtime: Optional["RuntimeContext"] = None,
    ):
        self.config       = config
        self.state        = state
        self.project_root = project_root
        self.docs_dir     = project_root / config.paths.docs
        self.state_path   = project_root / config.paths.state
        self._stage_state = state.get_stage(self.stage_name)
        self.runtime      = runtime

    # ── 추상 메서드 ──────────────────────────────────────────────────────────

    @abstractmethod
    def execute(self) -> None:
        """
        단계를 실행합니다.
        - agent를 호출하고 결과를 state에 기록합니다.
        - 완료 후 mark_awaiting()을 호출해 승인 대기 상태로 전환합니다.
        - 실패 또는 블로킹 이슈 발생 시 ApprovalGate.ask_decision()을 통해 사용자 결정을 받습니다.
        """

    # ── 공용 헬퍼 ────────────────────────────────────────────────────────────

    def print_header(self) -> None:
        console.print(Rule(f"[bold blue]{self.stage_label}[/bold blue]"))
        self.log(self.stage_label, event_type="stage_header")

    def get_agent(self):
        """이 단계에 할당된 agent 인스턴스를 반환합니다."""
        from harness.agents.registry import get_agent
        agent_name     = self.config.agent_for(self.stage_name)
        cli_template   = self.config.cli_template_for(agent_name)
        return get_agent(agent_name, cli_template=cli_template)

    def save_doc(self, filename: str, content: str) -> Path:
        """docs 디렉터리에 마크다운 문서를 저장합니다."""
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        path = self.docs_dir / filename
        path.write_text(content, encoding="utf-8")
        console.print(f"[dim]📄 문서 저장: {path}[/dim]")
        self.log(f"Document saved: {path}", event_type="doc_saved")
        return path

    def read_doc(self, filename: str) -> str:
        """docs 디렉터리에서 문서를 읽습니다."""
        path = self.docs_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def save_state(self) -> None:
        self.state.save(self.state_path)

    def log(self, message: str, *, event_type: str = "log") -> None:
        if self.runtime:
            self.runtime.log(message, event_type=event_type, stage=self.stage_name)

    def prompt_text(
        self,
        prompt: str,
        *,
        action_type: str,
        default: str = "",
        context: Optional[str] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> str:
        if not self.runtime or not self.runtime.interaction:
            raise RuntimeError("No interaction handler configured")
        self.log(f"Requesting {action_type} input", event_type="input_request")
        return self.runtime.interaction.text_input(
            stage=self.stage_name,
            action_type=action_type,
            prompt=prompt,
            default=default,
            context=context,
            metadata=metadata,
        )

    def request_approval(self, summary: str, doc_path: Optional[str] = None) -> tuple[bool, Optional[str]]:
        if not self.runtime or not self.runtime.interaction:
            raise RuntimeError("No interaction handler configured")
        self.log("Awaiting approval", event_type="approval_request")
        return self.runtime.interaction.approval(
            stage=self.stage_name,
            stage_label=self.stage_label,
            summary=summary,
            doc_path=doc_path,
        )

    def request_decision(self, question: str, *, context: Optional[str] = None) -> tuple[bool, Optional[str]]:
        if not self.runtime or not self.runtime.interaction:
            raise RuntimeError("No interaction handler configured")
        self.log("Decision needed", event_type="decision_request")
        return self.runtime.interaction.decision(
            stage=self.stage_name,
            question=question,
            context=context,
        )

    def confirm_retry(self) -> bool:
        if not self.runtime or not self.runtime.interaction:
            raise RuntimeError("No interaction handler configured")
        self.log("Retry decision requested", event_type="retry_request")
        return self.runtime.interaction.confirm_retry(
            stage=self.stage_name,
            stage_label=self.stage_label,
        )
