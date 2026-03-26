"""
ApprovalGate — 사람의 승인을 받는 인터랙티브 게이트
"""
from __future__ import annotations

from typing import Optional, Tuple

from harness.interaction import CLIInteractionHandler


class ApprovalGate:
    """단계 완료 후 사용자로부터 승인/거절을 받습니다."""

    _handler = CLIInteractionHandler()

    @staticmethod
    def request(
        stage_label: str,
        summary: str,
        doc_path: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        return ApprovalGate._handler.approval(
            stage="unknown",
            stage_label=stage_label,
            summary=summary,
            doc_path=doc_path,
        )

    @staticmethod
    def ask_decision(
        question: str,
        context: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        return ApprovalGate._handler.decision(stage="unknown", question=question, context=context)

    @staticmethod
    def confirm_loop(stage_label: str) -> bool:
        return ApprovalGate._handler.confirm_retry(stage="unknown", stage_label=stage_label)
