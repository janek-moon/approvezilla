"""
HarnessState — .harness/state.json 기반 상태 관리
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    PENDING           = "pending"
    RUNNING           = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    SKIPPED           = "skipped"


class JiraIssue(BaseModel):
    key:          str
    summary:      str
    issue_type:   str   # Epic / Story / Task / Sub-task
    parent_key:   Optional[str] = None
    url:          Optional[str] = None


class StageState(BaseModel):
    status:           StageStatus           = StageStatus.PENDING
    agent_used:       Optional[str]         = None
    started_at:       Optional[str]         = None
    completed_at:     Optional[str]         = None
    approved_at:      Optional[str]         = None
    rejected_at:      Optional[str]         = None
    output:           Optional[str]         = None   # agent 출력 요약
    doc_path:         Optional[str]         = None   # 생성된 문서 경로
    approval_notes:   Optional[str]         = None
    rejection_reason: Optional[str]         = None
    iteration:        int                   = 0      # 반복 횟수 (4→6 루프 등)
    jira_issues:      List[JiraIssue]       = Field(default_factory=list)
    log_excerpt:      List[str]             = Field(default_factory=list)
    metadata:         Dict[str, Any]        = Field(default_factory=dict)

    # ── 편의 메서드 ──────────────────────────────────────────────────────────

    def mark_running(self, agent: str) -> None:
        self.status     = StageStatus.RUNNING
        self.agent_used = agent
        self.started_at = _now()
        self.completed_at = None

    def mark_awaiting(self, output: Optional[str] = None) -> None:
        self.status       = StageStatus.AWAITING_APPROVAL
        self.completed_at = _now()
        if output:
            self.output = output

    def mark_approved(self, notes: Optional[str] = None) -> None:
        self.status       = StageStatus.APPROVED
        self.approved_at  = _now()
        self.approval_notes = notes

    def mark_rejected(self, reason: Optional[str] = None) -> None:
        self.status            = StageStatus.REJECTED
        self.rejected_at       = _now()
        self.rejection_reason  = reason
        self.iteration        += 1

    def reset_to_pending(self) -> None:
        self.status           = StageStatus.PENDING
        self.started_at       = None
        self.completed_at     = None
        self.approved_at      = None
        self.rejected_at      = None
        self.output           = None
        self.approval_notes   = None
        self.rejection_reason = None


class HarnessState(BaseModel):
    project:       str                     = "my-project"
    current_stage: str                     = "plan"
    created_at:    str                     = ""
    updated_at:    str                     = ""
    idea:          Optional[str]           = None   # Stage 1에서 입력받은 초기 아이디어
    run_id:        Optional[str]           = None
    run_status:    str                     = "pending"
    pending_action: Optional[Dict[str, Any]] = None
    active_log_path: Optional[str]         = None
    log_tail:      List[str]               = Field(default_factory=list)
    last_error:    Optional[str]           = None
    stages:        Dict[str, StageState]   = Field(default_factory=dict)

    # ── 직렬화 ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path) -> "HarnessState":
        from harness.config import STAGE_NAMES
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            obj = cls.model_validate(data)
        else:
            now = _now()
            obj = cls(
                created_at=now,
                updated_at=now,
            )
        # 누락된 stage 초기화
        for stage in STAGE_NAMES:
            if stage not in obj.stages:
                obj.stages[stage] = StageState()
        return obj

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = _now()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)

    # ── 접근자 ───────────────────────────────────────────────────────────────

    def get_stage(self, name: str) -> StageState:
        if name not in self.stages:
            self.stages[name] = StageState()
        return self.stages[name]

    def advance_to(self, stage: str) -> None:
        self.current_stage = stage
        self.updated_at    = _now()

    # ── 진행 상황 요약 ────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, str]:
        from harness.config import STAGE_NAMES, STAGE_LABELS
        result: Dict[str, str] = {}
        for name in STAGE_NAMES:
            st = self.get_stage(name)
            label = STAGE_LABELS.get(name, name)
            result[label] = st.status.value
        return result


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
