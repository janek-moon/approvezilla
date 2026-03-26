"""
Stage 6 — 리뷰 (Review)
git diff를 분석하여 기획 범위, 보안, SOLID, lint 등을 검토합니다.
실패 시 Stage 4로 회귀합니다.
"""
from __future__ import annotations

import subprocess
from typing import Tuple

from rich.console import Console
from rich.panel import Panel

from harness.stages.base import BaseStage

console = Console()

_REVIEW_PROMPT = """당신은 시니어 코드 리뷰어입니다.
다음 정보를 기반으로 철저한 코드 리뷰를 수행해 주세요.

## 기획서 (구현 범위 기준)
{plan}

## 디자인 문서
{design}

## git diff (변경된 코드)
```diff
{diff}
```

## 리뷰 항목 (각 항목별로 명확히 평가하세요)

### 1. 기획 범위 준수
- 기획서의 모든 기능이 구현되었는지 확인
- 범위 외 코드가 추가되지 않았는지 확인
- 미구현 항목 목록화

### 2. 보안 취약점
- SQL Injection, XSS, CSRF 취약점
- 인증/인가 누락
- 민감 데이터 노출 (하드코딩된 비밀번호, API 키 등)
- 의존성 취약점

### 3. SOLID 원칙 준수
- SRP: 단일 책임 원칙
- OCP: 개방/폐쇄 원칙
- LSP: 리스코프 치환 원칙
- ISP: 인터페이스 분리 원칙
- DIP: 의존성 역전 원칙

### 4. 코드 품질
- 코드 중복 (DRY 원칙)
- 복잡도 (순환 복잡도, 함수 길이)
- 명명 규칙 일관성
- 에러 핸들링 적절성
- 주석/문서화 충분성

### 5. 성능
- N+1 쿼리 문제
- 불필요한 연산/루프
- 메모리 누수 가능성

### 6. 테스트 커버리지
- 누락된 테스트 케이스

## 출력 형식
### 총평: [PASS / FAIL]
**PASS 기준**: 치명적 보안 취약점 없음, 기획 범위 80% 이상 구현, SOLID 원칙 심각한 위반 없음

각 항목별 평가를 구체적으로 작성하고,
수정이 필요한 코드는 수정 방법을 명시해 주세요.
"""


class ReviewStage(BaseStage):
    stage_name  = "review"
    stage_label = "6. 리뷰 (Review)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content   = self.read_doc("plan.md")
        design_content = self.read_doc("design.md")

        st.mark_running(agent.name)
        self.save_state()

        # git diff 수집
        diff = self._get_git_diff()
        if not diff:
            console.print("[yellow]git diff가 비어있습니다. 모든 변경사항이 커밋되었거나 git 저장소가 아닐 수 있습니다.[/yellow]")
            diff = "(변경사항 없음 또는 git 미초기화)"

        console.print(f"\n[dim]🤖 {agent.name} — 코드 리뷰 실행 중...[/dim]")

        prompt = _REVIEW_PROMPT.format(
            plan=plan_content,
            design=design_content,
            diff=diff[:8000],  # diff가 너무 길 경우 잘라냄
        )

        try:
            review_output = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
        except Exception as e:
            console.print(f"[red]리뷰 오류: {e}[/red]")
            proceed, _ = self.request_decision("리뷰 실행 실패. 계속 진행하시겠습니까?", context=str(e))
            if not proceed:
                raise
            review_output = f"리뷰 실패: {e}"

        # 리뷰 결과 표시
        console.print(Panel(review_output, title="[cyan]코드 리뷰 결과[/cyan]", border_style="cyan"))

        # PASS/FAIL 판정
        passed = "총평: PASS" in review_output or "### 총평: PASS" in review_output

        # 리뷰 문서 저장
        doc_path = self.save_doc("review.md", f"# 코드 리뷰\n\n{review_output}")
        st.doc_path = str(doc_path)
        st.mark_awaiting(output=review_output[:500])
        self.save_state()

        if not passed:
            console.print("[yellow]⚠ 리뷰 결과: FAIL — 구현 개선이 필요합니다.[/yellow]")
            retry = self.confirm_retry()
            if retry:
                st.mark_rejected("리뷰 FAIL — 4번으로 회귀")
                self.save_state()
                raise ReviewFailed("코드 리뷰 실패. 구현 단계로 돌아갑니다.")

        approved, notes = self.request_approval(
            summary=f"코드 리뷰 완료. 판정: {'PASS' if passed else 'FAIL(무시됨)'}",
            doc_path=str(doc_path),
        )

        if approved:
            st.mark_approved(notes)
            self.save_state()
            console.print("[bold green]✅ 리뷰 완료.[/bold green]\n")
        else:
            st.mark_rejected(notes)
            self.save_state()
            raise ReviewFailed(f"리뷰 단계 거절: {notes}")

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _get_git_diff(self) -> str:
        """git diff HEAD 또는 git diff (staged+unstaged) 수집."""
        for cmd in [
            ["git", "diff", "HEAD"],
            ["git", "diff"],
        ]:
            try:
                result = subprocess.run(
                    cmd, cwd=str(self.project_root),
                    capture_output=True, text=True, timeout=30,
                )
                if result.stdout.strip():
                    return result.stdout
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return ""


class ReviewFailed(Exception):
    """리뷰 실패 — Pipeline에서 Stage 4로 회귀 트리거"""
