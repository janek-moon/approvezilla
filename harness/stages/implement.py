"""
Stage 4 — 작업 진행 (Implement)
기획/디자인/작업 분할을 바탕으로 Codex(또는 Claude)로 기능을 구현합니다.
중간 이슈 발생 시 사용자 승인 후 진행합니다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from harness.stages.base import BaseStage

console = Console()

_IMPLEMENT_PROMPT = """당신은 시니어 소프트웨어 엔지니어입니다.
다음 문서들을 참고하여 기능을 구현해 주세요.

## 기획서
{plan}

## 디자인 문서
{design}

## 작업 목록
{tasks}

## 구현 지침
- SOLID 원칙을 준수하세요.
- 각 함수/클래스에 타입 힌트와 docstring을 추가하세요.
- 에러 핸들링을 철저히 하세요.
- 보안 취약점(SQL Injection, XSS, 인증 누락 등)을 주의하세요.
- 테스트 가능한 구조로 작성하세요.

{extra_instruction}

먼저 구현 계획을 설명한 후, 코드를 작성해 주세요.
"""

_ISSUE_PROMPT = """구현 중 다음 이슈가 발생했습니다:

## 이슈
{issue}

## 현재 구현 상태
{current_state}

## 사용자 지시사항
{instruction}

이슈를 해결하고 구현을 계속해 주세요.
"""


class ImplementStage(BaseStage):
    stage_name  = "implement"
    stage_label = "4. 작업 진행 (Implement)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content   = self.read_doc("plan.md")
        design_content = self.read_doc("design.md")
        tasks_content  = self.read_doc("tasks.md")

        if not plan_content:
            raise RuntimeError("docs/plan.md 가 없습니다.")

        # 추가 지시사항 입력
        console.print("[bold cyan]구현 시 특별히 주의할 사항이나 우선 구현할 항목이 있으면 입력하세요.[/bold cyan]")
        extra = self.prompt_text(
            "[dim]추가 지시사항 (없으면 Enter)[/dim]",
            action_type="implement_instruction",
            default="",
        )

        st.mark_running(agent.name)
        self.save_state()

        prompt = _IMPLEMENT_PROMPT.format(
            plan=plan_content,
            design=design_content,
            tasks=tasks_content,
            extra_instruction=extra.strip(),
        )

        console.print(f"\n[dim]🤖 {agent.name} 호출 중... (구현은 프로젝트 루트에서 실행됩니다)[/dim]")

        try:
            # 구현 단계는 interactive 모드로 실행 (codex는 파일을 직접 수정)
            if hasattr(agent, "run_interactive"):
                agent.run_interactive(prompt, cwd=str(self.project_root), runtime=self.runtime)
                output = "(interactive 실행 완료)"
            else:
                output = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
                console.print(Panel(output[:3000], title="[cyan]구현 결과[/cyan]", border_style="cyan"))

        except Exception as e:
            console.print(f"[red]구현 중 오류 발생: {e}[/red]")
            proceed, instruction = self.request_decision(
                "구현 중 오류가 발생했습니다. 지시사항을 입력 후 계속 진행하시겠습니까?",
                context=str(e),
            )
            if proceed and instruction:
                fix_prompt = _ISSUE_PROMPT.format(
                    issue=str(e),
                    current_state="오류 발생 전까지의 구현",
                    instruction=instruction,
                )
                output = agent.run(fix_prompt, cwd=str(self.project_root), runtime=self.runtime)
            elif not proceed:
                raise

        st.mark_awaiting(output=output[:500] if isinstance(output, str) else "(완료)")
        self.save_state()

        approved, notes = self.request_approval(
            summary="기능 구현이 완료되었습니다. 코드를 확인하고 승인해 주세요.",
        )

        if approved:
            st.mark_approved(notes)
            self.save_state()
            console.print("[bold green]✅ 구현 완료.[/bold green]\n")
        else:
            st.mark_rejected(notes)
            self.save_state()
            console.print("[yellow]구현 재작업이 필요합니다.[/yellow]\n")
            raise StageRejected(f"구현 거절: {notes}")


class StageRejected(Exception):
    """단계 거절 시 파이프라인에서 catch하여 처리"""
