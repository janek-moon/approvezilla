"""
Pipeline — 단계별 실행 오케스트레이터
4→5→6 루프 및 거절 시 회귀 로직을 포함합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rich.console import Console

from harness.config import STAGE_NAMES, STAGE_ORDER, HarnessConfig
from harness.runtime import RuntimeContext, StopRequestedError
from harness.stages.implement import StageRejected
from harness.stages.test import TestFailed
from harness.stages.review import ReviewFailed
from harness.stages.registry import get_stage_class
from harness.state import HarnessState, StageStatus

console = Console()

# 4→5→6 루프에서 회귀를 허용하는 최대 반복 횟수
MAX_IMPL_ITERATIONS = 10


class Pipeline:
    """하네스 워크플로 파이프라인."""

    def __init__(
        self,
        config: HarnessConfig,
        state: HarnessState,
        project_root: Path,
        runtime: Optional[RuntimeContext] = None,
    ):
        self.config       = config
        self.state        = state
        self.project_root = project_root
        self.state_path   = project_root / config.paths.state
        self.runtime      = runtime

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def run(
        self,
        from_stage: Optional[str] = None,
        to_stage:   Optional[str] = None,
        only_stage: Optional[str] = None,
    ) -> None:
        """
        파이프라인 실행.
        - only_stage: 해당 단계만 실행
        - from_stage: 해당 단계부터 실행
        - to_stage:   해당 단계까지 실행
        """
        if only_stage:
            stages_to_run = [only_stage]
        else:
            start = STAGE_ORDER.get(from_stage or STAGE_NAMES[0], 0)
            end   = STAGE_ORDER.get(to_stage   or STAGE_NAMES[-1], len(STAGE_NAMES) - 1)
            stages_to_run = STAGE_NAMES[start : end + 1]

        console.print(f"[bold]실행할 단계: {', '.join(stages_to_run)}[/bold]\n")
        if self.runtime:
            self.runtime.mark_run_started()
            self.runtime.log(f"Stages to run: {', '.join(stages_to_run)}", event_type="run_plan")

        try:
            pre_impl = [s for s in stages_to_run if s in ("plan", "design", "tasks")]
            for stage_name in pre_impl:
                self._run_stage(stage_name)

            impl_stages = [s for s in stages_to_run if s in ("implement", "test", "review")]
            if impl_stages:
                self._run_impl_loop(impl_stages)

            post_impl = [s for s in stages_to_run if s in ("docs", "close")]
            for stage_name in post_impl:
                self._run_stage(stage_name)
            if self.runtime:
                self.runtime.mark_run_finished("completed")
        except StopRequestedError as e:
            if self.runtime:
                self.runtime.mark_run_finished("failed", str(e))
            raise
        except Exception as e:
            if self.runtime:
                self.runtime.mark_run_finished("failed", str(e))
            raise

    def run_stage(self, stage_name: str) -> None:
        """단일 단계만 실행합니다."""
        self._run_stage(stage_name)

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _run_stage(self, stage_name: str) -> None:
        if self.runtime:
            self.runtime.raise_if_stopped()
        stage_cls = get_stage_class(stage_name)
        stage     = stage_cls(self.config, self.state, self.project_root, runtime=self.runtime)
        stage_st  = self.state.get_stage(stage_name)

        # 이미 승인된 단계는 건너뜀 (--force 없이)
        if stage_st.status == StageStatus.APPROVED:
            console.print(f"[dim]⏭ {stage_name} — 이미 승인됨. 건너뜁니다.[/dim]")
            if self.runtime:
                self.runtime.log(f"Skipped approved stage {stage_name}", event_type="stage_skipped", stage=stage_name)
            return

        self.state.advance_to(stage_name)
        self.state.save(self.state_path)
        if self.runtime:
            self.runtime.log(f"Starting stage {stage_name}", event_type="stage_started", stage=stage_name)
            self.runtime.publish("stage_started", {"stage": stage_name, "message": f"Starting stage {stage_name}"})
        stage.execute()
        if self.runtime:
            self.runtime.log(
                f"Completed stage {stage_name} with status {stage_st.status.value}",
                event_type="stage_completed",
                stage=stage_name,
            )
            self.runtime.publish(
                "stage_completed",
                {
                    "stage": stage_name,
                    "status": stage_st.status.value,
                    "message": f"Completed stage {stage_name} with status {stage_st.status.value}",
                },
            )

    def _run_impl_loop(self, stages: List[str]) -> None:
        """implement → test → review 루프. 실패 시 implement로 회귀."""
        iteration = 0

        while iteration < MAX_IMPL_ITERATIONS:
            iteration += 1
            console.print(f"\n[bold cyan]─── 구현 루프 #{iteration} ───[/bold cyan]")
            if self.runtime:
                self.runtime.log(f"Implement loop #{iteration}", event_type="loop", stage="implement")

            try:
                for stage_name in stages:
                    # 이전 루프에서 승인된 단계 초기화 (재실행 필요)
                    stage_st = self.state.get_stage(stage_name)
                    if stage_st.status not in (StageStatus.APPROVED, StageStatus.PENDING):
                        stage_st.reset_to_pending()
                        self.state.save(self.state_path)

                    self._run_stage(stage_name)

                # 모든 단계 통과
                console.print(f"[bold green]✅ 구현 루프 완료 (총 {iteration}회)[/bold green]")
                return

            except (TestFailed, ReviewFailed, StageRejected) as e:
                console.print(f"[yellow]↩  {e} — 구현 단계로 돌아갑니다...[/yellow]\n")
                # implement 단계를 초기화하여 재실행 준비
                if "implement" in stages:
                    self.state.get_stage("implement").reset_to_pending()
                if "test" in stages:
                    self.state.get_stage("test").reset_to_pending()
                if "review" in stages:
                    self.state.get_stage("review").reset_to_pending()
                self.state.save(self.state_path)

        console.print(f"[red]최대 반복 횟수({MAX_IMPL_ITERATIONS})에 도달했습니다. 수동으로 확인하세요.[/red]")
