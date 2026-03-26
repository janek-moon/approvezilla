"""
harness CLI — 메인 엔트리포인트
사용법: harness [COMMAND] [OPTIONS]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from harness.config import STAGE_LABELS, STAGE_NAMES, HarnessConfig
from harness.interaction import CLIInteractionHandler
from harness.pipeline import Pipeline
from harness.runtime import RuntimeContext
from harness.state import HarnessState, StageStatus

app     = typer.Typer(name="harness", help="AI Agent 개발 하네스 — 8단계 워크플로 오케스트레이터")
console = Console()

# ── 전역 옵션 ─────────────────────────────────────────────────────────────────

_ROOT_OPT = typer.Option(
    ".", "--root", "-r",
    help="프로젝트 루트 디렉터리 (기본값: 현재 디렉터리)",
)
_CONFIG_OPT = typer.Option(
    "harness.yml", "--config", "-c",
    help="설정 파일 경로",
)


def _load(root: str, config_file: str):
    """config, state, pipeline 로드."""
    project_root = Path(root).resolve()
    config_path  = project_root / config_file
    config       = HarnessConfig.load(config_path)
    state_path   = project_root / config.paths.state
    state        = HarnessState.load(state_path)
    state.project = config.project.name
    logs_dir     = project_root / config.paths.logs
    log_path     = logs_dir / f"{state.run_id or 'cli'}.log"
    runtime      = RuntimeContext(
        state=state,
        state_path=state_path,
        log_path=log_path,
        interaction=CLIInteractionHandler(),
    )
    pipeline     = Pipeline(config, state, project_root, runtime=runtime)
    return config, state, pipeline, project_root, state_path, runtime


# ── 명령어 ────────────────────────────────────────────────────────────────────

@app.command()
def init(
    name:   str = typer.Option("my-project", "--name", "-n", help="프로젝트 이름"),
    root:   str = _ROOT_OPT,
    config_file: str = _CONFIG_OPT,
):
    """현재 디렉터리에 harness를 초기화합니다."""
    project_root = Path(root).resolve()
    config_path  = project_root / config_file

    if config_path.exists():
        console.print(f"[yellow]이미 {config_file}이 존재합니다.[/yellow]")
        overwrite = typer.confirm("덮어쓰겠습니까?", default=False)
        if not overwrite:
            raise typer.Abort()

    config = HarnessConfig()
    config.project.name = name
    config.save(config_path)

    # docs/.harness 디렉터리 생성
    (project_root / config.paths.docs).mkdir(parents=True, exist_ok=True)
    (project_root / Path(config.paths.state).parent).mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]✅ harness 초기화 완료![/bold green]")
    console.print(f"   설정 파일: {config_path}")
    console.print(f"   다음 명령으로 시작: [bold]harness run[/bold]\n")


@app.command()
def run(
    stage:  Optional[str] = typer.Option(None, "--stage",  "-s", help="특정 단계만 실행 (예: plan, design, implement)"),
    from_:  Optional[str] = typer.Option(None, "--from",   "-f", help="이 단계부터 실행"),
    to:     Optional[str] = typer.Option(None, "--to",     "-t", help="이 단계까지 실행"),
    force:  bool          = typer.Option(False, "--force",        help="이미 승인된 단계도 재실행"),
    root:   str           = _ROOT_OPT,
    config_file: str      = _CONFIG_OPT,
):
    """하네스 파이프라인을 실행합니다."""
    config, state, pipeline, project_root, state_path, _ = _load(root, config_file)

    # --force: 지정된 단계의 승인 상태 초기화
    if force:
        target_stages = _resolve_stages(stage, from_, to)
        for s in target_stages:
            state.get_stage(s).reset_to_pending()
        state.save(state_path)
        console.print(f"[yellow]--force: {', '.join(target_stages)} 단계를 초기화했습니다.[/yellow]")

    try:
        pipeline.run(
            from_stage=from_,
            to_stage=to,
            only_stage=stage,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]사용자에 의해 중단되었습니다.[/yellow]")
        state.save(state_path)
        sys.exit(0)


@app.command()
def status(
    root:        str = _ROOT_OPT,
    config_file: str = _CONFIG_OPT,
):
    """현재 하네스 진행 상태를 표시합니다."""
    config, state, _, _, _, _ = _load(root, config_file)

    STATUS_STYLE = {
        StageStatus.PENDING:           ("⬜", "dim"),
        StageStatus.RUNNING:           ("🔄", "cyan"),
        StageStatus.AWAITING_APPROVAL: ("⏸", "yellow"),
        StageStatus.APPROVED:          ("✅", "green"),
        StageStatus.REJECTED:          ("❌", "red"),
        StageStatus.SKIPPED:           ("⏭", "dim"),
    }

    table = Table(title=f"[bold]{config.project.name}[/bold] — 진행 현황", show_lines=True)
    table.add_column("단계",        style="bold", width=22)
    table.add_column("상태",        width=16)
    table.add_column("Agent",       width=12)
    table.add_column("반복",        width=6, justify="right")
    table.add_column("문서",        width=28)

    for name in STAGE_NAMES:
        label = STAGE_LABELS.get(name, name)
        st    = state.get_stage(name)
        emoji, style = STATUS_STYLE.get(st.status, ("?", ""))
        table.add_row(
            label,
            f"[{style}]{emoji} {st.status.value}[/{style}]",
            st.agent_used or "-",
            str(st.iteration) if st.iteration else "-",
            st.doc_path or "-",
        )

    console.print(table)
    console.print(f"[dim]현재 단계: {state.current_stage}[/dim]")
    if state.idea:
        console.print(f"[dim]아이디어: {state.idea[:80]}[/dim]")


@app.command()
def approve(
    stage:       Optional[str] = typer.Option(None, "--stage", "-s", help="승인할 단계 (기본: 현재 단계)"),
    notes:       Optional[str] = typer.Option(None, "--notes", "-n", help="승인 메모"),
    root:        str           = _ROOT_OPT,
    config_file: str           = _CONFIG_OPT,
):
    """현재 단계(또는 지정 단계)를 승인합니다."""
    config, state, _, _, state_path, _ = _load(root, config_file)
    target = stage or state.current_stage
    st = state.get_stage(target)

    if st.status not in (StageStatus.AWAITING_APPROVAL, StageStatus.RUNNING, StageStatus.REJECTED):
        console.print(f"[yellow]{target} 단계는 현재 승인 가능한 상태가 아닙니다. (현재: {st.status.value})[/yellow]")
        raise typer.Exit(1)

    st.mark_approved(notes)
    state.save(state_path)
    console.print(f"[bold green]✅ {STAGE_LABELS.get(target, target)} 승인 완료.[/bold green]")


@app.command()
def reject(
    stage:       Optional[str] = typer.Option(None, "--stage", "-s"),
    reason:      Optional[str] = typer.Option(None, "--reason", "-r", help="거절 사유"),
    root:        str           = _ROOT_OPT,
    config_file: str           = _CONFIG_OPT,
):
    """현재 단계(또는 지정 단계)를 거절합니다."""
    config, state, _, _, state_path, _ = _load(root, config_file)
    target = stage or state.current_stage
    st = state.get_stage(target)

    st.mark_rejected(reason)
    state.save(state_path)
    console.print(f"[bold red]❌ {STAGE_LABELS.get(target, target)} 거절됨. 사유: {reason or '없음'}[/bold red]")


@app.command()
def reset(
    stage:       str = typer.Argument(..., help="초기화할 단계"),
    root:        str = _ROOT_OPT,
    config_file: str = _CONFIG_OPT,
):
    """특정 단계부터 상태를 초기화합니다."""
    _, state, _, _, state_path, _ = _load(root, config_file)

    if stage not in STAGE_NAMES:
        console.print(f"[red]알 수 없는 단계: {stage}[/red]")
        raise typer.Exit(1)

    start_idx = STAGE_NAMES.index(stage)
    to_reset  = STAGE_NAMES[start_idx:]

    confirm = typer.confirm(f"{', '.join(to_reset)} 단계를 초기화하시겠습니까?")
    if not confirm:
        raise typer.Abort()

    for s in to_reset:
        state.get_stage(s).reset_to_pending()
    state.current_stage = stage
    state.save(state_path)
    console.print(f"[green]{', '.join(to_reset)} 단계가 초기화되었습니다.[/green]")


@app.command()
def config(
    show:        bool          = typer.Option(False, "--show",   help="현재 설정 출력"),
    set_agent:   Optional[str] = typer.Option(None,  "--agent",  help="단계별 agent 설정 (예: implement=codex)"),
    root:        str           = _ROOT_OPT,
    config_file: str           = _CONFIG_OPT,
):
    """하네스 설정을 조회하거나 수정합니다."""
    project_root = Path(root).resolve()
    config_path  = project_root / config_file
    cfg          = HarnessConfig.load(config_path)

    if set_agent:
        try:
            stage_name, agent_name = set_agent.split("=")
            cfg.agents.stages.set(stage_name.strip(), agent_name.strip())
            cfg.save(config_path)
            console.print(f"[green]✅ {stage_name} → {agent_name} 설정 완료.[/green]")
        except ValueError:
            console.print("[red]형식 오류. 예: --agent implement=codex[/red]")
            raise typer.Exit(1)

    if show or not set_agent:
        import yaml
        console.print(yaml.dump(cfg.model_dump(), allow_unicode=True, default_flow_style=False))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    root: str = _ROOT_OPT,
    config_file: str = _CONFIG_OPT,
):
    """웹 운영 콘솔을 실행합니다."""
    import uvicorn
    from harness.web import create_app

    uvicorn.run(
        create_app(root=root, config_file=config_file),
        host=host,
        port=port,
        reload=False,
    )


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _resolve_stages(
    stage:  Optional[str],
    from_:  Optional[str],
    to:     Optional[str],
) -> list[str]:
    if stage:
        return [stage]
    from harness.config import STAGE_ORDER
    start = STAGE_ORDER.get(from_ or STAGE_NAMES[0], 0)
    end   = STAGE_ORDER.get(to    or STAGE_NAMES[-1], len(STAGE_NAMES) - 1)
    return STAGE_NAMES[start : end + 1]


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
