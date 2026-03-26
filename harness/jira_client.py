"""
JiraClient — Jira REST API v3 연동
환경변수: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth
from rich.console import Console

from harness.state import JiraIssue

console = Console()


class JiraClient:
    def __init__(
        self,
        url:         Optional[str] = None,
        email:       Optional[str] = None,
        api_token:   Optional[str] = None,
        project_key: Optional[str] = None,
    ):
        self.base_url    = (url         or os.getenv("JIRA_URL",         "")).rstrip("/")
        self.email       = email        or os.getenv("JIRA_EMAIL",       "")
        self.api_token   = api_token    or os.getenv("JIRA_API_TOKEN",   "")
        self.project_key = project_key  or os.getenv("JIRA_PROJECT_KEY", "")
        self._auth       = HTTPBasicAuth(self.email, self.api_token)
        self._headers    = {"Accept": "application/json", "Content-Type": "application/json"}

    # ── 연결 확인 ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        try:
            r = requests.get(
                f"{self.base_url}/rest/api/3/myself",
                auth=self._auth, headers=self._headers, timeout=10
            )
            return r.status_code == 200
        except Exception:
            return False

    # ── 이슈 생성 ─────────────────────────────────────────────────────────────

    def create_issue(
        self,
        summary:    str,
        issue_type: str,             # "Epic" | "Story" | "Task" | "Sub-task"
        description: str = "",
        parent_key:  Optional[str] = None,
        labels:      Optional[List[str]] = None,
    ) -> JiraIssue:
        payload: Dict[str, Any] = {
            "fields": {
                "project":   {"key": self.project_key},
                "summary":   summary,
                "issuetype": {"name": issue_type},
                "description": {
                    "version": 1,
                    "type":    "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                },
            }
        }

        if labels:
            payload["fields"]["labels"] = labels

        # 부모 이슈 연결 (Story → Epic, Sub-task → Task)
        if parent_key:
            if issue_type == "Sub-task":
                payload["fields"]["parent"] = {"key": parent_key}
            else:
                payload["fields"]["parent"] = {"key": parent_key}

        r = requests.post(
            f"{self.base_url}/rest/api/3/issue",
            json=payload, auth=self._auth, headers=self._headers, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        key  = data["key"]
        url  = f"{self.base_url}/browse/{key}"
        console.print(f"  [green]✔ Jira 이슈 생성:[/green] [{issue_type}] {key} — {summary}")
        return JiraIssue(key=key, summary=summary, issue_type=issue_type, parent_key=parent_key, url=url)

    # ── 이슈 업데이트 ─────────────────────────────────────────────────────────

    def update_issue(self, key: str, fields: Dict[str, Any]) -> None:
        r = requests.put(
            f"{self.base_url}/rest/api/3/issue/{key}",
            json={"fields": fields}, auth=self._auth, headers=self._headers, timeout=30,
        )
        r.raise_for_status()

    # ── 이슈 조회 ─────────────────────────────────────────────────────────────

    def get_issue(self, key: str) -> Dict[str, Any]:
        r = requests.get(
            f"{self.base_url}/rest/api/3/issue/{key}",
            auth=self._auth, headers=self._headers, timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ── 계층 이슈 일괄 생성 ───────────────────────────────────────────────────

    def create_hierarchy(self, breakdown: Dict[str, Any]) -> List[JiraIssue]:
        """
        breakdown 예시:
        {
          "epics": [
            {
              "summary": "에픽 제목",
              "description": "...",
              "stories": [
                {
                  "summary": "스토리 제목",
                  "description": "...",
                  "tasks": [
                    {
                      "summary": "태스크 제목",
                      "description": "...",
                      "subtasks": [{"summary": "...", "description": "..."}]
                    }
                  ]
                }
              ]
            }
          ]
        }
        """
        created: List[JiraIssue] = []

        for epic_data in breakdown.get("epics", []):
            epic = self.create_issue(
                summary=epic_data["summary"],
                issue_type="Epic",
                description=epic_data.get("description", ""),
            )
            created.append(epic)

            for story_data in epic_data.get("stories", []):
                story = self.create_issue(
                    summary=story_data["summary"],
                    issue_type="Story",
                    description=story_data.get("description", ""),
                    parent_key=epic.key,
                )
                created.append(story)

                for task_data in story_data.get("tasks", []):
                    task = self.create_issue(
                        summary=task_data["summary"],
                        issue_type="Task",
                        description=task_data.get("description", ""),
                        parent_key=story.key,
                    )
                    created.append(task)

                    for sub_data in task_data.get("subtasks", []):
                        sub = self.create_issue(
                            summary=sub_data["summary"],
                            issue_type="Sub-task",
                            description=sub_data.get("description", ""),
                            parent_key=task.key,
                        )
                        created.append(sub)

        return created
