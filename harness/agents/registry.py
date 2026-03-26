"""
AgentRegistry — 이름으로 agent 인스턴스를 생성하는 팩토리
"""
from __future__ import annotations

from typing import Dict, Type

from harness.agents.base import BaseAgent
from harness.agents.claude import ClaudeAgent
from harness.agents.codex import CodexAgent
from harness.agents.coderabbit import CodeRabbitAgent

_REGISTRY: Dict[str, Type[BaseAgent]] = {
    "claude":      ClaudeAgent,
    "codex":       CodexAgent,
    "coderabbit":  CodeRabbitAgent,
}


def get_agent(name: str, cli_template: Optional[str] = None) -> BaseAgent:
    """
    agent 이름으로 인스턴스를 반환합니다.
    cli_template이 있으면 생성자에 전달합니다.
    """
    from typing import Optional  # noqa: F401 (re-import for clarity)

    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"알 수 없는 agent: '{name}'. "
            f"사용 가능한 agent: {', '.join(_REGISTRY.keys())}"
        )

    if cli_template:
        return cls(cli_template=cli_template)  # type: ignore[call-arg]
    return cls()


def list_agents() -> list[str]:
    return list(_REGISTRY.keys())
