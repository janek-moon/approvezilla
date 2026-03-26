"""
CodeRabbitAgent — CodeRabbitAI CLI 래퍼
CodeRabbit은 주로 GitHub PR webhook 방식으로 동작하지만,
CLI 모드(coderabbit review)가 있을 경우 이를 활용합니다.
CLI가 없는 경우 ClaudeAgent로 폴백하여 코드 리뷰를 수행합니다.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from rich.console import Console

from harness.agents.base import BaseAgent

console = Console()

# coderabbit CLI가 지원하는 실제 커맨드 (설치 여부에 따라 달라짐)
_CODERABBIT_BIN = "coderabbit"


class CodeRabbitAgent(BaseAgent):
    name = "coderabbit"

    def __init__(self, cli_template: str = "coderabbit review"):
        self._template = cli_template
        self._available = shutil.which(_CODERABBIT_BIN) is not None

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        extra_args: Optional[list] = None,
        runtime=None,
    ) -> str:
        if self._available:
            return self._run_native(cwd, runtime=runtime)
        return self._run_fallback(prompt, cwd, runtime=runtime)

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _run_native(self, cwd: Optional[str], runtime=None) -> str:
        """coderabbit CLI가 설치된 경우 직접 실행."""
        cmd = self._template.split()
        return self._exec(cmd, cwd=cwd, capture=True, runtime=runtime)

    def _run_fallback(self, prompt: str, cwd: Optional[str], runtime=None) -> str:
        """coderabbit CLI가 없을 경우 claude로 폴백."""
        console.print(
            "[yellow]⚠  coderabbit CLI를 찾을 수 없어 Claude Code로 코드 리뷰를 대신 수행합니다.[/yellow]"
        )
        from harness.agents.claude import ClaudeAgent
        fallback = ClaudeAgent()
        return fallback.run(prompt, cwd=cwd, runtime=runtime)

    @property
    def is_available(self) -> bool:
        return self._available
