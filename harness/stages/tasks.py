"""
Stage 3 — 작업 분할 (Tasks)
디자인 문서를 바탕으로 작업을 분할하고 Jira 이슈를 생성합니다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from harness.jira_client import JiraClient
from harness.stages.base import BaseStage

console = Console()

_TASKS_PROMPT = """당신은 Agile 프로젝트 매니저입니다.
다음 기획서와 디자인 문서를 바탕으로 구현 작업을 계층적으로 분할해 주세요.

## 기획서
{plan}

## 디자인 문서
{design}

## 작업 분할 규칙
- Epic: 큰 기능 단위 (1~2주 이상)
- Story: 사용자 관점의 기능 단위 (2~5일)
- Task: 기술적 구현 단위 (1~2일)
- Sub-task: Task의 세부 작업 (반나절~1일)

## 출력 형식 (반드시 이 JSON 형식으로만 출력)
```json
{{
  "epics": [
    {{
      "summary": "에픽 제목",
      "description": "에픽 설명",
      "stories": [
        {{
          "summary": "스토리 제목",
          "description": "스토리 설명 (As a user, I want...)",
          "tasks": [
            {{
              "summary": "태스크 제목",
              "description": "기술적 구현 설명",
              "subtasks": [
                {{"summary": "서브태스크 제목", "description": "상세 작업 설명"}}
              ]
            }}
          ]
        }}
      ]
    }}
  ]
}}
```
"""


class TasksStage(BaseStage):
    stage_name  = "tasks"
    stage_label = "3. 작업 분할 (Tasks)"

    def execute(self) -> None:
        self.print_header()

        st    = self._stage_state
        agent = self.get_agent()

        plan_content   = self.read_doc("plan.md")
        design_content = self.read_doc("design.md")

        if not plan_content or not design_content:
            raise RuntimeError("기획(plan.md) 또는 디자인(design.md) 문서가 없습니다.")

        st.mark_running(agent.name)
        self.save_state()

        breakdown: Dict[str, Any] = {}
        iteration = 0

        while True:
            console.print(f"\n[dim]🤖 {agent.name} 호출 중...[/dim]")

            prompt = _TASKS_PROMPT.format(plan=plan_content, design=design_content)
            if iteration > 0:
                console.print("[bold cyan]작업 분할에 대한 피드백을 입력하세요.[/bold cyan]")
                feedback = self.prompt_text("[yellow]피드백[/yellow]", action_type="feedback_input")
                prompt += f"\n\n## 이전 결과에 대한 수정 요청\n{feedback}"

            try:
                raw_output = agent.run(prompt, cwd=str(self.project_root), runtime=self.runtime)
                breakdown  = self._parse_json(raw_output)
            except Exception as e:
                console.print(f"[red]Agent 오류: {e}[/red]")
                proceed, _ = self.request_decision("Agent 호출 실패. 계속 진행하시겠습니까?", context=str(e))
                if not proceed:
                    raise

            # 작업 목록 표시
            self._print_breakdown(breakdown)

            # 문서 저장
            tasks_md = self._to_markdown(breakdown)
            doc_path = self.save_doc("tasks.md", tasks_md)
            st.doc_path = str(doc_path)
            st.metadata["breakdown"] = breakdown

            # Jira 연동
            jira_created = []
            if self.config.jira.enabled and self.config.jira.is_configured:
                create_jira = self.prompt_text(
                    "Jira 이슈를 생성하시겠습니까? (y/n)",
                    action_type="jira_confirm",
                    default="y",
                ).lower().startswith("y")

                if create_jira:
                    jira_created = self._create_jira_issues(breakdown)
                    st.jira_issues = jira_created
            else:
                console.print("[dim]Jira가 비활성화되어 있거나 설정이 없어 이슈 생성을 건너뜁니다.[/dim]")

            st.mark_awaiting(output=f"{len(breakdown.get('epics', []))} 에픽, 작업 트리 생성 완료")
            self.save_state()

            approved, notes = self.request_approval(
                summary=f"작업 분할 완료. Jira 이슈 {len(jira_created)}개 생성됨.",
                doc_path=str(doc_path),
            )

            if approved:
                st.mark_approved(notes)
                self.save_state()
                console.print("[bold green]✅ 작업 분할 완료. 문서: docs/tasks.md[/bold green]\n")
                return
            else:
                st.mark_rejected(notes)
                self.save_state()
                iteration += 1
                st.iteration = iteration

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """agent 출력에서 JSON 블록을 추출합니다."""
        # ```json ... ``` 블록 추출
        match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
        if match:
            text = match.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 실패: {e}\n원본:\n{text[:500]}")

    def _create_jira_issues(self, breakdown: Dict[str, Any]):
        client = JiraClient(
            url=self.config.jira.url,
            email=self.config.jira.email,
            api_token=self.config.jira.api_token,
            project_key=self.config.jira.project_key,
        )
        if not client.ping():
            console.print("[red]Jira 연결 실패. 설정을 확인하세요.[/red]")
            return []
        console.print("[cyan]Jira 이슈 생성 중...[/cyan]")
        return client.create_hierarchy(breakdown)

    @staticmethod
    def _print_breakdown(breakdown: Dict[str, Any]) -> None:
        table = Table(title="작업 분할 결과", show_lines=True)
        table.add_column("유형", style="bold cyan", width=10)
        table.add_column("제목")

        for epic in breakdown.get("epics", []):
            table.add_row("Epic",  epic.get("summary", ""))
            for story in epic.get("stories", []):
                table.add_row("  Story", story.get("summary", ""))
                for task in story.get("tasks", []):
                    table.add_row("    Task", task.get("summary", ""))
                    for sub in task.get("subtasks", []):
                        table.add_row("      Sub-task", sub.get("summary", ""))

        console.print(table)

    @staticmethod
    def _to_markdown(breakdown: Dict[str, Any]) -> str:
        lines = ["# 작업 분할\n"]
        for epic in breakdown.get("epics", []):
            lines.append(f"## Epic: {epic['summary']}")
            if epic.get("description"):
                lines.append(f"> {epic['description']}\n")
            for story in epic.get("stories", []):
                lines.append(f"### Story: {story['summary']}")
                if story.get("description"):
                    lines.append(f"> {story['description']}\n")
                for task in story.get("tasks", []):
                    lines.append(f"#### Task: {task['summary']}")
                    if task.get("description"):
                        lines.append(f"> {task['description']}\n")
                    for sub in task.get("subtasks", []):
                        lines.append(f"- **Sub-task:** {sub['summary']}")
                        if sub.get("description"):
                            lines.append(f"  > {sub['description']}")
                    lines.append("")
        return "\n".join(lines)
