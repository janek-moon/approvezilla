"""
CodexAgent — OpenAI Codex CLI 래퍼
CLI: codex "<prompt>"
     codex --full-auto "<prompt>"   (승인 없이 자동 실행)
"""
from __future__ import annotations

import shlex
from typing import Optional

from harness.agents.base import BaseAgent


class CodexAgent(BaseAgent):
    name = "codex"

    def __init__(
        self,
        cli_template: str = 'codex "{prompt}"',
        full_auto: bool = False,
    ):
        self._template  = cli_template
        self._full_auto = full_auto

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        extra_args: Optional[list] = None,
        runtime=None,
    ) -> str:
        cmd = self._build_cmd(prompt, extra_args)
        return self._exec(cmd, cwd=cwd, capture=True, runtime=runtime)

    def run_interactive(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        full_auto: Optional[bool] = None,
        runtime=None,
    ) -> None:
        """Interactive 또는 --full-auto 모드로 실행."""
        use_auto = full_auto if full_auto is not None else self._full_auto
        if use_auto:
            cmd = ["codex", "--full-auto", prompt]
        else:
            cmd = ["codex", prompt]
        self._exec(cmd, cwd=cwd, capture=False, runtime=runtime)

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _build_cmd(self, prompt: str, extra_args: Optional[list]) -> list[str]:
        raw = self._template.replace("{prompt}", prompt)
        cmd = shlex.split(raw)
        if cmd and cmd[0] == "codex" and (len(cmd) == 1 or cmd[1] != "exec"):
            # `codex "<prompt>"` is interactive-only and fails without a TTY.
            # For captured/non-interactive stage runs, normalize to `codex exec`.
            cmd.insert(1, "exec")
        if len(cmd) > 1 and cmd[0] == "codex" and cmd[1] == "exec" and "--skip-git-repo-check" not in cmd:
            cmd.insert(2, "--skip-git-repo-check")
        if self._full_auto and "--full-auto" not in cmd:
            # non-interactive 모드에서도 full-auto 플래그 추가
            idx = cmd.index(cmd[0]) + 1
            cmd.insert(idx, "--full-auto")
        if extra_args:
            cmd.extend(extra_args)
        return cmd
