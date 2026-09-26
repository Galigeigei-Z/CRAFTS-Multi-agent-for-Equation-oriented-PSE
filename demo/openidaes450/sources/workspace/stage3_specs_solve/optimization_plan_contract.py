"""Shared validation for registered deterministic OptimizationPlanIR runners."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def validate_optimization_plan(
    path: Path | None,
    template: dict[str, Any],
    *,
    label: str,
) -> None:
    """Require an exact registered plan while preserving direct-run compatibility."""

    if path is None:
        return
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if candidate != template:
        raise ValueError(f"OptimizationPlanIR does not match the registered {label} template")


def plan_provenance(path: Path | None, template: dict[str, Any]) -> dict[str, Any]:
    return {
        "optimization_plan_file": str(path) if path else None,
        "optimization_plan_variables": list(template.get("variables_to_unfix") or []),
        "optimization_plan_target_dof": template.get("target_dof"),
    }
