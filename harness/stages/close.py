"""
Stage 8 — 검토 승인 후 종료 (Close)
전체 작업에 대한 최종 브리핑을 생성하고 종료합니다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from harness.config import STAGE_LABELS, STAGE_NAMES
from harness.stages.base import BaseStage
from harness.state import StageStatus

console = Console()

_BRIEFING_PROMPT = """당신은 프로젝트 매니저입니다.
다음 문서들을 기반으로 최종 브리핑 문서를 작성해 주세요.

## 기획서
{plan}

## 디자인 문서
{design}

## 작업 분할
{tasks}

## 코드 리뷰 결과
{review}

## 최종 브리핑 포함 항목
1. **프로젝트 요약** — 무엇을 만들었는지 1~2 문장
2. **구현된 주요 기능** — 기획 대비 실제 구현 현황
3. **기술 스택 최종 정리**
4. **미구현 항목** — 향후 작업 필요한 내용
5. **알려진 이슈** — 리뷰에서 발견된 미해결 이슈
6. **다음 단계 제안** — 후속 작업 권장사항
"""


class CloseStage(BaseStage):
    stage_name  = "close"
    stage_label = "8. 검토/종료 (Close)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        # ── 전체 진행 현황 출력 ─────────────────────────────────────────────
        self._print_progress_summary()

        # ── 최종 브리핑 생성 ────────────────────────────────────────────────
        console.print(f"\n[dim]🤖 {agent.name} — 최종 브리핑 생성 중...[/dim]")
        st.mark_running(agent.name)
        self.save_state()

        plan_content   = self.read_doc("plan.md")
        design_content = self.read_doc("design.md")
        tasks_content  = self.read_doc("tasks.md")
        review_content = self.read_doc("review.md")

        prompt = _BRIEFING_PROMPT.format(
            plan=plan_content,
            design=design_content,
            tasks=tasks_content,
            review=review_content,
        )

        try:
            briefing = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
        except Exception as e:
            console.print(f"[red]브리핑 생성 오류: {e}[/red]")
            briefing = f"브리핑 생성 실패: {e}"

        console.print(Panel(briefing, title="[bold cyan]🏁 최종 브리핑[/bold cyan]", border_style="bold cyan"))

        # 브리핑 문서 저장
        doc_path = self.save_doc("final_briefing.md", f"# 최종 브리핑\n\n{briefing}")
        st.doc_path = str(doc_path)
        st.mark_awaiting(output=briefing[:500])
        self.save_state()

        # ── 최종 승인 ───────────────────────────────────────────────────────
        approved, notes = self.request_approval(
            summary="모든 단계가 완료되었습니다. 최종 승인 후 작업이 종료됩니다.",
            doc_path=str(doc_path),
        )

        if approved:
            st.mark_approved(notes)
            self.save_state()
            console.rule("[bold green]🎉 모든 작업이 완료되었습니다! 🎉[/bold green]")
            console.print(f"[dim]최종 브리핑: docs/final_briefing.md[/dim]")
        else:
            st.mark_rejected(notes)
            self.save_state()
            console.print("[yellow]최종 승인이 거절되었습니다. 원하는 단계부터 다시 실행하세요.[/yellow]")

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _print_progress_summary(self) -> None:
        """전체 단계 진행 현황을 테이블로 출력합니다."""
        table = Table(title="전체 작업 진행 현황", show_lines=True)
        table.add_column("단계", style="bold")
        table.add_column("상태")
        table.add_column("반복 횟수", justify="right")
        table.add_column("Agent")

        STATUS_EMOJI = {
            StageStatus.PENDING:           "⬜ 대기",
            StageStatus.RUNNING:           "🔄 진행중",
            StageStatus.AWAITING_APPROVAL: "⏸ 승인대기",
            StageStatus.APPROVED:          "✅ 승인",
            StageStatus.REJECTED:          "❌ 거절",
            StageStatus.SKIPPED:           "⏭ 건너뜀",
        }

        for name in STAGE_NAMES:
            label = STAGE_LABELS.get(name, name)
            stage_st = self.state.get_stage(name)
            table.add_row(
                label,
                STATUS_EMOJI.get(stage_st.status, stage_st.status.value),
                str(stage_st.iteration) if stage_st.iteration else "-",
                stage_st.agent_used or "-",
            )

        console.print(table)
