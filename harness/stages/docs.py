"""
Stage 7 — 문서화 (Docs)
기획/디자인 vs 실제 구현의 차이를 분석하고 문서를 최신화합니다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from harness.stages.base import BaseStage

console = Console()

_DOCS_PROMPT = """당신은 테크니컬 라이터입니다.
기획/설계 문서와 실제 구현(코드 리뷰 결과)을 비교하여 문서를 최신화해 주세요.

## 원본 기획서
{plan}

## 원본 디자인 문서
{design}

## 코드 리뷰 결과 (실제 구현 내용 반영)
{review}

## 작업
1. 기획서와 구현 사이의 차이점을 파악하세요.
2. 실제 구현을 기준으로 다음 문서들을 업데이트해 주세요:
   - **README.md**: 프로젝트 개요, 설치/실행 방법, 주요 기능
   - **docs/plan.md**: 변경된 기능/범위 반영
   - **docs/design.md**: 실제 아키텍처/API 변경사항 반영
   - **docs/CHANGELOG.md**: 구현된 내용 요약

각 문서를 `---FILE: <파일명>---` 구분자로 구분하여 출력해 주세요.

예시:
---FILE: README.md---
# 프로젝트명
...

---FILE: docs/CHANGELOG.md---
# Changelog
...
"""


class DocsStage(BaseStage):
    stage_name  = "docs"
    stage_label = "7. 문서화 (Docs)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content   = self.read_doc("plan.md")
        design_content = self.read_doc("design.md")
        review_content = self.read_doc("review.md")

        st.mark_running(agent.name)
        self.save_state()

        console.print(f"\n[dim]🤖 {agent.name} — 문서 업데이트 중...[/dim]")

        prompt = _DOCS_PROMPT.format(
            plan=plan_content,
            design=design_content,
            review=review_content,
        )

        try:
            output = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
        except Exception as e:
            console.print(f"[red]문서화 오류: {e}[/red]")
            proceed, _ = self.request_decision("문서화 실패. 계속 진행하시겠습니까?", context=str(e))
            if not proceed:
                raise
            output = ""

        # 문서 파일 분할 저장
        saved_files = self._save_doc_files(output)

        console.print(Panel(
            "\n".join(f"✅ {f}" for f in saved_files) or "(저장된 파일 없음)",
            title="[cyan]업데이트된 문서[/cyan]",
            border_style="cyan",
        ))

        st.mark_awaiting(output=f"업데이트된 파일: {', '.join(saved_files)}")
        self.save_state()

        approved, notes = self.request_approval(
            summary=f"문서 업데이트 완료. 업데이트된 파일: {len(saved_files)}개",
        )

        if approved:
            st.mark_approved(notes)
            self.save_state()
            console.print("[bold green]✅ 문서화 완료.[/bold green]\n")
        else:
            st.mark_rejected(notes)
            self.save_state()
            # 문서화는 재작업 가능하므로 예외 없이 반복 허용
            console.print("[yellow]문서화 재작업이 필요합니다. 다시 실행하세요.[/yellow]")

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _save_doc_files(self, output: str) -> list[str]:
        """---FILE: xxx--- 구분자로 문서를 분할하여 저장합니다."""
        import re
        saved = []

        parts = re.split(r"---FILE:\s*(.+?)---", output)
        # parts = ["앞부분", "파일명1", "내용1", "파일명2", "내용2", ...]
        it = iter(parts[1:])  # 앞부분 무시
        for filename, content in zip(it, it):
            filename = filename.strip()
            content  = content.strip()
            if not filename or not content:
                continue

            target = self.project_root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            console.print(f"[dim]📄 저장: {target}[/dim]")
            saved.append(filename)

        return saved
