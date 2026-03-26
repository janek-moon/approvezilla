# Approvezilla

`Approvezilla`는 AI agent 기반 개발 워크플로를 단계별로 실행하는 Python 오케스트레이터입니다.  
기획부터 구현, 테스트, 리뷰, 문서화, 종료 브리핑까지 8단계를 관리하며, 이제 CLI뿐 아니라 로컬 웹 운영 콘솔에서도 실행/승인/로그 확인/Jira 연동을 처리할 수 있습니다.

## What It Does

- 8단계 개발 파이프라인 실행
  - `plan -> design -> tasks -> implement -> test -> review -> docs -> close`
- 단계별 agent 매핑
  - Claude, Codex, CodeRabbit CLI 래핑
- 상태 저장
  - `.harness/state.json`
- 문서 산출물 저장
  - `docs/`
- Jira 계층 이슈 생성
  - Epic / Story / Task / Sub-task
- 웹 운영 콘솔
  - 실행 시작/중단
  - 단계 상태 확인
  - 실시간 로그 확인
  - 승인/거절/추가 입력 처리
  - Jira 연결 테스트 및 tasks 결과 기반 이슈 생성

## Installation

```bash
python -m pip install -e .
```

개발 도구까지 함께 설치하려면:

```bash
python -m pip install -e .[dev]
```

## Quick Start

초기화:

```bash
harness init --name my-project
```

전체 파이프라인 실행:

```bash
harness run
```

특정 단계만 실행:

```bash
harness run --stage plan
```

구간 실행:

```bash
harness run --from design --to review
```

이미 승인된 단계를 강제로 다시 실행:

```bash
harness run --stage tasks --force
```

현재 상태 확인:

```bash
harness status
```

웹 콘솔 실행:

```bash
harness serve --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`으로 접속하면 됩니다.

## Web Console

웹 콘솔은 로컬 단일 사용자 운영 콘솔입니다.

- Run Control
  - 전체 실행, 특정 stage 실행, from/to 실행, force reset
- Pending Action
  - 승인/거절
  - 피드백 입력
  - 구현 지시사항 입력
  - 재시도 여부 결정
- Live Log
  - 현재 실행 로그 tail
  - background run 이벤트 반영
- Jira Panel
  - 연결 테스트
  - tasks 단계 산출물 기반 이슈 생성

실시간 업데이트는 SSE 기반입니다.

## Configuration

기본 설정 파일은 `harness.yml`입니다.

예시:

```yaml
project:
  name: my-project
  description: null
agents:
  default: claude
  stages:
    plan: claude
    design: claude
    tasks: claude
    implement: codex
    test: claude
    review: coderabbit
    docs: claude
    close: claude
  cli:
    claude: claude -p "{prompt}"
    codex: codex "{prompt}"
    coderabbit: coderabbit review
jira:
  url: null
  email: null
  api_token: null
  project_key: null
paths:
  docs: docs
  state: .harness/state.json
  logs: .harness/logs
```

## Jira Integration

Jira 연동은 `tasks` 단계와 웹 콘솔에서 사용됩니다.

필수 설정:

- `jira.url`
- `jira.email`
- `jira.api_token`
- `jira.project_key`

웹 콘솔에서 할 수 있는 작업:

- 연결 테스트
- 현재 `tasks` 결과를 기반으로 Jira 이슈 생성

생성 대상:

- Epic
- Story
- Task
- Sub-task

## State And Logs

상태 파일:

- `.harness/state.json`

주요 필드:

- `run_id`
- `run_status`
- `pending_action`
- `active_log_path`
- `log_tail`
- `last_error`

로그 파일:

- `.harness/logs/`

웹 콘솔은 이 상태와 로그를 기반으로 현재 실행 상태를 보여줍니다.

## CLI Commands

초기화:

```bash
harness init
```

실행:

```bash
harness run
```

상태:

```bash
harness status
```

단계 승인:

```bash
harness approve --stage plan --notes "ok"
```

단계 거절:

```bash
harness reject --stage review --reason "needs changes"
```

단계 초기화:

```bash
harness reset implement
```

설정 확인:

```bash
harness config --show
```

단계별 agent 변경:

```bash
harness config --agent implement=codex
```

웹 서버 실행:

```bash
harness serve
```

## Development

문법 검증:

```bash
python -m compileall harness
```

테스트:

```bash
python -m pytest -q
```

lint:

```bash
ruff check .
```

type check:

```bash
mypy harness
```

## Current Limitations

- 1차 구현은 로컬 단일 사용자 기준입니다.
- 웹 콘솔 인증/멀티유저 권한 관리는 아직 없습니다.
- 웹 테스트는 `fastapi`가 설치된 환경에서만 실행됩니다.
- 실제 agent CLI 설치 여부는 별도로 보장되어야 합니다.

## Project Structure

```text
harness/
  agents/        Agent CLI wrappers
  stages/        Pipeline stage implementations
  static/        Web console assets
  templates/     Web console templates
  cli.py         Typer entrypoint
  pipeline.py    Stage orchestration
  runtime.py     Runtime events/logging/interaction
  web.py         FastAPI web console
  state.py       Persistent state models
  config.py      YAML config models
docs/            Generated workflow documents
```
