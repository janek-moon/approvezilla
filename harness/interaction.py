"""
Interactive handlers for CLI and stage-level prompting helpers.
"""
from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from harness.runtime import InteractionHandler

console = Console()


class CLIInteractionHandler(InteractionHandler):
    """Interactive handler backed by Rich prompts."""

    def text_input(
        self,
        *,
        stage: str,
        action_type: str,
        prompt: str,
        default: str = "",
        context: Optional[str] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> str:
        if context:
            console.print(Panel(context, title="[yellow]참고[/yellow]", border_style="yellow"))
        return Prompt.ask(prompt, default=default)

    def approval(
        self,
        *,
        stage: str,
        stage_label: str,
        summary: str,
        doc_path: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        console.rule(f"[bold yellow]⏸  {stage_label} — 승인 요청[/bold yellow]")
        console.print(Panel(summary, title="[cyan]단계 결과 요약[/cyan]", border_style="cyan"))
        if doc_path:
            console.print(f"[dim]📄 생성된 문서: {doc_path}[/dim]\n")
        approved = Confirm.ask("[bold green]✔ 승인하시겠습니까?[/bold green]", default=True)
        if approved:
            notes = Prompt.ask("[dim]승인 메모 (없으면 Enter)[/dim]", default="").strip() or None
            console.print("[bold green]✅ 승인되었습니다.[/bold green]\n")
            return True, notes
        notes = Prompt.ask("[bold red]거절 사유를 입력하세요[/bold red]", default="").strip() or None
        console.print("[bold red]❌ 거절되었습니다. 해당 단계를 다시 진행합니다.[/bold red]\n")
        return False, notes

    def decision(
        self,
        *,
        stage: str,
        question: str,
        context: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        console.rule("[bold yellow]⚠  중간 이슈 — 결정 필요[/bold yellow]")
        if context:
            console.print(Panel(context, title="[yellow]이슈 내용[/yellow]", border_style="yellow"))
        console.print(f"[bold]{question}[/bold]\n")
        proceed = Confirm.ask("계속 진행하시겠습니까?", default=False)
        instruction = None
        if proceed:
            instruction = Prompt.ask("추가 지시사항 (없으면 Enter)", default="").strip() or None
        else:
            console.print("[yellow]작업이 중단되었습니다.[/yellow]\n")
        return proceed, instruction

    def confirm_retry(self, *, stage: str, stage_label: str) -> bool:
        return Confirm.ask(
            f"[bold red]{stage_label} 실패[/bold red] — 4번(작업 진행)부터 다시 진행하시겠습니까?",
            default=True,
        )
