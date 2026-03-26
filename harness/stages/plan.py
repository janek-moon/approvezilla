"""
Stage 1 — 기획 (Plan)
아이디어를 입력받아 Claude와 반복 대화로 기획서를 완성합니다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from harness.stages.base import BaseStage

console = Console()

_PLAN_PROMPT = """당신은 시니어 소프트웨어 기획자입니다.
다음 아이디어를 바탕으로 구체적인 기획서를 마크다운 형식으로 작성해 주세요.

## 아이디어
{idea}

## 기획서 포함 항목
1. 목적 및 배경
2. 주요 기능 (기능 목록 + 우선순위)
3. 사용자 시나리오 (User Flow)
4. 비기능 요구사항 (성능, 보안, 확장성 등)
5. 제약 사항 및 가정
6. 성공 기준 (Definition of Done)

{feedback}
"""

_REFINE_PROMPT = """이전 기획서를 다음 피드백을 반영하여 개선해 주세요.

## 이전 기획서
{previous}

## 피드백
{feedback}

동일한 마크다운 형식으로 전체 기획서를 다시 작성해 주세요.
"""


class PlanStage(BaseStage):
    stage_name  = "plan"
    stage_label = "1. 기획 (Plan)"

    def execute(self) -> None:
        self.print_header()

        st = self._stage_state
        agent = self.get_agent()

        # ── 초기 아이디어 입력 ──────────────────────────────────────────────
        if not self.state.idea:
            console.print("[bold cyan]어떤 기능/아이디어를 구현하고 싶으신가요?[/bold cyan]")
            idea = self.prompt_text("[green]아이디어 입력[/green]", action_type="idea_input")
            self.state.idea = idea.strip()
            self.save_state()

        st.mark_running(agent.name)
        self.save_state()

        # ── 반복 기획 루프 ──────────────────────────────────────────────────
        plan_content: str = ""
        iteration = 0

        while True:
            console.print(f"\n[dim]🤖 {agent.name} 호출 중...[/dim]")

            if iteration == 0:
                prompt = _PLAN_PROMPT.format(idea=self.state.idea, feedback="")
            else:
                console.print("[bold cyan]기획서에 대한 피드백을 입력하세요.[/bold cyan]")
                feedback = self.prompt_text("[yellow]피드백[/yellow]", action_type="feedback_input")
                prompt = _REFINE_PROMPT.format(previous=plan_content, feedback=feedback)

            try:
                plan_content = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
            except Exception as e:
                console.print(f"[red]Agent 오류: {e}[/red]")
                proceed, _ = self.request_decision(
                    "Agent 호출 실패. 계속 진행하시겠습니까?",
                    context=str(e),
                )
                if not proceed:
                    raise

            # 기획서 표시
            console.print(Panel(plan_content, title="[cyan]기획서 초안[/cyan]", border_style="cyan"))

            # 승인 요청
            doc_path = self.save_doc("plan.md", plan_content)
            st.doc_path = str(doc_path)
            st.mark_awaiting(output=plan_content[:500])
            self.save_state()

            approved, notes = self.request_approval(
                summary=f"기획서가 작성되었습니다.\n\n**아이디어:** {self.state.idea}",
                doc_path=str(doc_path),
            )

            if approved:
                st.mark_approved(notes)
                self.save_state()
                console.print("[bold green]✅ 기획 완료. 문서: docs/plan.md[/bold green]\n")
                return
            else:
                st.mark_rejected(notes)
                self.save_state()
                iteration += 1
                st.iteration = iteration
