"""
BaseAgent — 모든 agent 래퍼의 추상 기반 클래스
"""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from typing import Optional

from rich.console import Console

console = Console()


class AgentError(RuntimeError):
    """agent 실행 실패 시 발생"""


class BaseAgent(ABC):
    """agent CLI 래퍼의 공통 인터페이스."""

    name: str = "base"

    # ── 추상 메서드 ──────────────────────────────────────────────────────────

    @abstractmethod
    def run(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        extra_args: Optional[list] = None,
        runtime=None,
    ) -> str:
        """
        Non-interactive 실행: agent 출력 문자열을 반환합니다.
        실패 시 AgentError를 raise합니다.
        """

    # ── 공용 유틸리티 ────────────────────────────────────────────────────────

    @staticmethod
    def _exec(
        cmd: list[str],
        cwd: Optional[str] = None,
        capture: bool = True,
        runtime=None,
    ) -> str:
        """
        subprocess를 실행합니다.
        capture=True  → stdout 캡처 후 반환
        capture=False → 터미널에 직접 출력 (interactive 모드)
        """
        console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
        if runtime:
            summary = cmd[0]
            if len(cmd) > 1 and not cmd[1].startswith("-"):
                summary = f"{summary} {cmd[1]}"
            runtime.log(f"Running command: {summary}", event_type="command")

        if capture:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if runtime:
                runtime.register_process(process)
            lines: list[str] = []
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip("\n")
                lines.append(line)
                if runtime:
                    runtime.log(line, event_type="agent_output")
            return_code = process.wait()
            if runtime:
                runtime.clear_process(process)
            if return_code != 0:
                err = "\n".join(lines).strip()
                raise AgentError(
                    f"[{' '.join(cmd[:2])}] 실행 실패 (code {return_code}):\n{err}"
                )
            return "\n".join(lines).strip()
        else:
            # stdout/stderr 를 현재 터미널로 그대로 전달
            process = subprocess.Popen(cmd, cwd=cwd)
            if runtime:
                runtime.register_process(process)
            return_code = process.wait()
            if runtime:
                runtime.clear_process(process)
            if return_code != 0:
                raise AgentError(
                    f"[{' '.join(cmd[:2])}] 실행 실패 (code {return_code})"
                )
            return ""

    def __repr__(self) -> str:
        return f"<Agent:{self.name}>"
