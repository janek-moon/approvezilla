"""
Stage 2 — 디자인 (Design)
기획서를 바탕으로 아키텍처 및 제품 디자인 문서를 생성합니다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from harness.stages.base import BaseStage

console = Console()

_DESIGN_PROMPT = """당신은 시니어 소프트웨어 아키텍트입니다.
다음 기획서를 바탕으로 아키텍처 및 제품 디자인 문서를 마크다운 형식으로 작성해 주세요.

## 기획서
{plan}

## 디자인 문서 포함 항목
1. 시스템 아키텍처 개요 (컴포넌트 다이어그램 — Mermaid 형식)
2. 기술 스택 및 선택 이유
3. 데이터 모델 / ERD (Mermaid 형식)
4. API 설계 (엔드포인트, 요청/응답 예시)
5. 주요 플로우 다이어그램 (Mermaid 시퀀스/플로우차트)
6. 디렉터리 구조
7. 보안 고려사항
8. 확장성 및 성능 전략
9. 개발 환경 설정 가이드

{feedback}
"""

_REFINE_PROMPT = """이전 디자인 문서를 다음 피드백을 반영하여 개선해 주세요.

## 이전 디자인
{previous}

## 피드백
{feedback}

동일한 마크다운 형식으로 전체 디자인 문서를 다시 작성해 주세요.
"""


class DesignStage(BaseStage):
    stage_name  = "design"
    stage_label = "2. 디자인 (Design)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content = self.read_doc("plan.md")
        if not plan_content:
            raise RuntimeError("docs/plan.md 파일이 없습니다. 먼저 기획(plan) 단계를 완료하세요.")

        st.mark_running(agent.name)
        self.save_state()

        design_content: str = ""
        iteration = 0

        while True:
            console.print(f"\n[dim]🤖 {agent.name} 호출 중...[/dim]")

            if iteration == 0:
                prompt = _DESIGN_PROMPT.format(plan=plan_content, feedback="")
            else:
                console.print("[bold cyan]디자인 문서에 대한 피드백을 입력하세요.[/bold cyan]")
                feedback = self.prompt_text("[yellow]피드백[/yellow]", action_type="feedback_input")
                prompt = _REFINE_PROMPT.format(previous=design_content, feedback=feedback)

            try:
                design_content = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
            except Exception as e:
                console.print(f"[red]Agent 오류: {e}[/red]")
                proceed, _ = self.request_decision("Agent 호출 실패. 계속 진행하시겠습니까?", context=str(e))
                if not proceed:
                    raise

            console.print(Panel(design_content[:2000] + ("..." if len(design_content) > 2000 else ""),
                                title="[cyan]디자인 문서 초안[/cyan]", border_style="cyan"))

            doc_path = self.save_doc("design.md", design_content)
            st.doc_path = str(doc_path)
            st.mark_awaiting(output=design_content[:500])
            self.save_state()

            approved, notes = self.request_approval(
                summary="아키텍처 및 디자인 문서가 작성되었습니다.",
                doc_path=str(doc_path),
            )

            if approved:
                st.mark_approved(notes)
                self.save_state()
                console.print("[bold green]✅ 디자인 완료. 문서: docs/design.md[/bold green]\n")
                return
            else:
                st.mark_rejected(notes)
                self.save_state()
                iteration += 1
                st.iteration = iteration
