"""
ClaudeAgent — Claude Code CLI 래퍼
CLI: claude -p "<prompt>"          (non-interactive, stdout 캡처)
     claude "<prompt>"             (interactive — 터미널 직접 출력)
"""
from __future__ import annotations

import shlex
from typing import Optional

from harness.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"

    def __init__(self, cli_template: str = 'claude -p "{prompt}"'):
        self._template = cli_template

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        extra_args: Optional[list] = None,
        runtime=None,
    ) -> str:
        """Non-interactive: 결과를 문자열로 반환."""
        cmd = self._build_cmd(prompt, extra_args)
        return self._exec(cmd, cwd=cwd, capture=True, runtime=runtime)

    def run_interactive(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        runtime=None,
    ) -> None:
        """Interactive: 터미널에 직접 출력 (대화형)."""
        cmd = ["claude", prompt]
        self._exec(cmd, cwd=cwd, capture=False, runtime=runtime)

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _build_cmd(self, prompt: str, extra_args: Optional[list]) -> list[str]:
        # 템플릿에서 {prompt} 치환
        raw = self._template.replace("{prompt}", prompt)
        cmd = shlex.split(raw)
        if extra_args:
            cmd.extend(extra_args)
        return cmd
