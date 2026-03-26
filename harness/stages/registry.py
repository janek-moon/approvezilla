"""
StageRegistry — 이름으로 Stage 클래스를 반환하는 팩토리
"""
from __future__ import annotations

from typing import Dict, Type

from harness.stages.base import BaseStage
from harness.stages.plan import PlanStage
from harness.stages.design import DesignStage
from harness.stages.tasks import TasksStage
from harness.stages.implement import ImplementStage
from harness.stages.test import TestStage
from harness.stages.review import ReviewStage
from harness.stages.docs import DocsStage
from harness.stages.close import CloseStage

_REGISTRY: Dict[str, Type[BaseStage]] = {
    "plan":      PlanStage,
    "design":    DesignStage,
    "tasks":     TasksStage,
    "implement": ImplementStage,
    "test":      TestStage,
    "review":    ReviewStage,
    "docs":      DocsStage,
    "close":     CloseStage,
}


def get_stage_class(name: str) -> Type[BaseStage]:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"알 수 없는 stage: '{name}'. "
            f"사용 가능: {', '.join(_REGISTRY.keys())}"
        )
    return cls


def list_stages() -> list[str]:
    return list(_REGISTRY.keys())
