"""
HarnessConfig — harness.yml 로드 및 설정 모델
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field

# ── 단계 순서 ──────────────────────────────────────────────────────────────
STAGE_NAMES = ["plan", "design", "tasks", "implement", "test", "review", "docs", "close"]
STAGE_ORDER: Dict[str, int] = {name: i for i, name in enumerate(STAGE_NAMES)}

STAGE_LABELS = {
    "plan":      "1. 기획",
    "design":    "2. 디자인",
    "tasks":     "3. 작업 분할",
    "implement": "4. 작업 진행",
    "test":      "5. 테스트",
    "review":    "6. 리뷰",
    "docs":      "7. 문서화",
    "close":     "8. 검토/종료",
}


# ── 하위 설정 모델 ──────────────────────────────────────────────────────────

class AgentStagesConfig(BaseModel):
    """단계별 사용할 agent 이름"""
    plan:      str = "claude"
    design:    str = "claude"
    tasks:     str = "claude"
    implement: str = "codex"
    test:      str = "claude"
    review:    str = "coderabbit"
    docs:      str = "claude"
    close:     str = "claude"

    def get(self, stage: str) -> str:
        return getattr(self, stage, "claude")

    def set(self, stage: str, agent: str) -> None:
        if stage not in STAGE_NAMES:
            raise ValueError(f"Unknown stage: {stage}")
        object.__setattr__(self, stage, agent)


class AgentCLIConfig(BaseModel):
    """각 agent CLI 명령어 템플릿.
    {prompt}  → 실제 프롬프트 문자열로 치환됨
    {cwd}     → 작업 디렉터리로 치환됨 (옵션)
    """
    claude:      str = 'claude -p "{prompt}"'
    codex:       str = 'codex exec "{prompt}"'
    coderabbit:  str = "coderabbit review"

    def get(self, name: str) -> str:
        return getattr(self, name, 'claude -p "{prompt}"')


class AgentConfig(BaseModel):
    default: str = "claude"
    stages:  AgentStagesConfig = Field(default_factory=AgentStagesConfig)
    cli:     AgentCLIConfig    = Field(default_factory=AgentCLIConfig)


class JiraConfig(BaseModel):
    enabled:     bool          = False
    url:         Optional[str] = None   # https://org.atlassian.net
    email:       Optional[str] = None
    api_token:   Optional[str] = None
    project_key: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return self.enabled and all([self.url, self.email, self.api_token, self.project_key])


class ProjectConfig(BaseModel):
    name:        str           = "my-project"
    description: Optional[str] = None


class PathsConfig(BaseModel):
    docs:  str = "docs"
    state: str = ".harness/state.json"
    logs:  str = ".harness/logs"


# ── 최상위 설정 ─────────────────────────────────────────────────────────────

class HarnessConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    agents:  AgentConfig   = Field(default_factory=AgentConfig)
    jira:    JiraConfig    = Field(default_factory=JiraConfig)
    paths:   PathsConfig   = Field(default_factory=PathsConfig)

    # ── 로드/저장 ───────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path = Path("harness.yml")) -> "HarnessConfig":
        if path.exists():
            with open(path, encoding="utf-8") as f:
                raw: Dict[str, Any] = yaml.safe_load(f) or {}
            return cls.model_validate(raw)
        return cls()

    def save(self, path: Path = Path("harness.yml")) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=False),
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

    # ── 헬퍼 ───────────────────────────────────────────────────────────────

    def agent_for(self, stage: str) -> str:
        return self.agents.stages.get(stage) or self.agents.default

    def cli_template_for(self, agent_name: str) -> str:
        return self.agents.cli.get(agent_name)
