"""
Stage 5 — 테스트 (Test)
단위/통합 테스트 생성 및 정적 코드 분석을 수행합니다.
실패 시 Stage 4로 회귀합니다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from harness.stages.base import BaseStage

console = Console()

_TEST_GEN_PROMPT = """당신은 QA 엔지니어입니다.
다음 기획서와 구현 코드를 기반으로 단위 테스트 및 통합 테스트를 작성해 주세요.

## 기획서
{plan}

## 테스트 작성 지침
- pytest를 사용하세요.
- 각 주요 함수/클래스에 대한 단위 테스트를 작성하세요.
- Happy path와 Edge case를 모두 커버하세요.
- Mock을 적절히 사용하세요.
- 테스트 파일은 tests/ 디렉터리에 위치해야 합니다.

현재 프로젝트 루트에서 테스트를 생성하고 실행해 주세요.
"""

# 정적 분석 도구 목록
_STATIC_TOOLS: List[Tuple[str, List[str]]] = [
    ("ruff",   ["ruff", "check", "."]),
    ("mypy",   ["mypy", ".", "--ignore-missing-imports"]),
    ("bandit", ["bandit", "-r", ".", "-ll"]),
]


class TestStage(BaseStage):
    stage_name  = "test"
    stage_label = "5. 테스트 (Test)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content = self.read_doc("plan.md")
        st.mark_running(agent.name)
        self.save_state()

        # ── 1. 테스트 코드 생성 ─────────────────────────────────────────────
        console.print("\n[cyan]📝 테스트 코드 생성 중...[/cyan]")
        prompt = _TEST_GEN_PROMPT.format(plan=plan_content)
        try:
            if hasattr(agent, "run_interactive"):
                agent.run_interactive(prompt, cwd=str(self.project_root), runtime=self.runtime)
            else:
                output = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
                console.print(Panel(output[:2000], title="테스트 생성 결과", border_style="cyan"))
        except Exception as e:
            console.print(f"[red]테스트 생성 오류: {e}[/red]")

        # ── 2. 테스트 실행 ──────────────────────────────────────────────────
        test_passed, test_output = self._run_tests()

        # ── 3. 정적 코드 분석 ───────────────────────────────────────────────
        static_results = self._run_static_analysis()

        # ── 결과 출력 ───────────────────────────────────────────────────────
        self._print_results(test_passed, test_output, static_results)

        all_passed = test_passed and all(ok for _, ok, _ in static_results)

        summary = (
            f"테스트 {'✅ 통과' if test_passed else '❌ 실패'}\n"
            + "\n".join(
                f"{tool}: {'✅' if ok else '❌'}"
                for tool, ok, _ in static_results
            )
        )

        st.mark_awaiting(output=summary)
        self.save_state()

        if not all_passed:
            retry = self.confirm_retry()
            if retry:
                st.mark_rejected("테스트/분석 실패 — 4번으로 회귀")
                self.save_state()
                raise TestFailed("테스트 또는 정적 분석 실패. 구현 단계로 돌아갑니다.")
            else:
                console.print("[yellow]테스트 실패를 무시하고 계속합니다.[/yellow]")

        approved, notes = self.request_approval(summary=summary)
        if approved:
            st.mark_approved(notes)
            self.save_state()
            console.print("[bold green]✅ 테스트 완료.[/bold green]\n")
        else:
            st.mark_rejected(notes)
            self.save_state()
            raise TestFailed(f"테스트 단계 거절: {notes}")

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _run_tests(self) -> Tuple[bool, str]:
        """pytest 실행."""
        console.print("\n[cyan]🧪 pytest 실행 중...[/cyan]")
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--tb=short", "-q"],
                cwd=str(self.project_root),
                capture_output=True, text=True, timeout=120,
            )
            passed = result.returncode == 0
            output = result.stdout + result.stderr
            status = "✅ 통과" if passed else "❌ 실패"
            console.print(f"pytest: {status}")
            return passed, output
        except FileNotFoundError:
            console.print("[yellow]pytest가 설치되어 있지 않습니다.[/yellow]")
            return True, "(pytest 미설치)"
        except subprocess.TimeoutExpired:
            return False, "테스트 시간 초과 (120초)"

    def _run_static_analysis(self) -> List[Tuple[str, bool, str]]:
        """정적 분석 도구 실행."""
        results = []
        for tool, cmd in _STATIC_TOOLS:
            console.print(f"\n[cyan]🔍 {tool} 실행 중...[/cyan]")
            try:
                r = subprocess.run(
                    cmd, cwd=str(self.project_root),
                    capture_output=True, text=True, timeout=60,
                )
                passed = r.returncode == 0
                output = r.stdout + r.stderr
                status = "✅" if passed else "⚠️ 이슈 발견"
                console.print(f"{tool}: {status}")
                results.append((tool, passed, output))
            except FileNotFoundError:
                console.print(f"[dim]{tool} 미설치 — 건너뜁니다.[/dim]")
            except subprocess.TimeoutExpired:
                results.append((tool, False, "시간 초과"))
        return results

    @staticmethod
    def _print_results(
        test_passed: bool,
        test_output: str,
        static_results: List[Tuple[str, bool, str]],
    ) -> None:
        table = Table(title="테스트 / 정적 분석 결과", show_lines=True)
        table.add_column("항목", style="bold")
        table.add_column("결과")
        table.add_column("상세")

        table.add_row(
            "pytest",
            "✅ 통과" if test_passed else "❌ 실패",
            test_output[-300:] if test_output else "",
        )
        for tool, ok, out in static_results:
            table.add_row(
                tool,
                "✅ 통과" if ok else "⚠️ 이슈",
                out[-200:] if out else "",
            )
        console.print(table)


class TestFailed(Exception):
    """테스트 실패 — Pipeline에서 Stage 4로 회귀 트리거"""
