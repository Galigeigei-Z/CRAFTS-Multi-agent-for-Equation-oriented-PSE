"""Versioned case catalog used by the web index and maintenance tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
CASE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*$")
RUN_STATUSES = {"draft", "source_verified", "validated", "solved", "optimized", "retired"}
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "experiment" / "case_registry" / "registry.json"


class RegistryError(ValueError):
    """Raised when the case registry violates its data contract."""


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"case registry does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"invalid case registry JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryError("case registry root must be an object")
    return data


def case_records(registry: dict[str, Any], suite: str | None = None) -> list[dict[str, Any]]:
    records = registry.get("cases", [])
    if not isinstance(records, list):
        return []
    selected = [record for record in records if isinstance(record, dict)]
    if suite:
        selected = [record for record in selected if suite in record.get("suites", [])]
    return sorted(selected, key=lambda record: int(record.get("order", 0)))


def catalog_entries(registry: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (str(record["case_key"]), str(record["label"]))
        for record in case_records(registry)
        if record.get("lifecycle", "active") != "retired"
    ]


def selected_manifest_records(registry: dict[str, Any], suite: str | None = None) -> list[dict[str, str]]:
    """Return selected-run rows for one suite or the complete registry."""
    records: list[dict[str, str]] = []
    for case in case_records(registry, suite):
        selection = case.get("selection")
        if not isinstance(selection, dict) or not selection.get("run_id"):
            continue
        row = {str(key): str(value) if value is not None else "" for key, value in selection.items()}
        row["case_key"] = str(case["case_key"])
        row.setdefault("family", str(case.get("family") or ""))
        row["case_label"] = str(case.get("label") or case["case_key"])
        row["case_ecosystem"] = str(case.get("ecosystem") or "")
        records.append(row)
    return records


def validate_registry(
    registry: dict[str, Any],
    *,
    root: Path | None = None,
    check_artifacts: bool = False,
) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    records = registry.get("cases")
    if not isinstance(records, list):
        return [*errors, "cases must be an array"]

    seen: set[str] = set()
    orders: set[int] = set()
    for index, record in enumerate(records):
        prefix = f"cases[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        case_key = str(record.get("case_key") or "")
        if not CASE_KEY_RE.fullmatch(case_key):
            errors.append(f"{prefix}.case_key is invalid: {case_key!r}")
        if case_key in seen:
            errors.append(f"duplicate case_key: {case_key}")
        seen.add(case_key)
        if not str(record.get("label") or "").strip():
            errors.append(f"{case_key or prefix}: label is required")
        if not str(record.get("family") or "").strip():
            errors.append(f"{case_key or prefix}: family is required")
        if not str(record.get("process_family") or "").strip():
            errors.append(f"{case_key or prefix}: process_family is required")
        suites = record.get("suites")
        if not isinstance(suites, list) or len(suites) != len(set(suites)):
            errors.append(f"{case_key or prefix}: suites must be a unique array")
        order = record.get("order")
        if not isinstance(order, int) or order < 0:
            errors.append(f"{case_key or prefix}: order must be a non-negative integer")
        elif order in orders:
            errors.append(f"duplicate order: {order}")
        else:
            orders.add(order)

        selection = record.get("selection")
        if selection is None:
            continue
        if not isinstance(selection, dict):
            errors.append(f"{case_key}: selection must be an object")
            continue
        status = str(selection.get("status") or selection.get("selected_status") or "")
        if status not in RUN_STATUSES:
            errors.append(f"{case_key}: invalid selection status {status!r}")
        if status in {"solved", "optimized"}:
            for field in ("run_id", "topology_ir_file", "spec_ir_file", "solve_report_file"):
                if not str(selection.get(field) or "").strip():
                    errors.append(f"{case_key}: {field} is required for {status}")
        if check_artifacts and root:
            for field in (
                "topology_ir_file",
                "spec_ir_file",
                "solve_report_file",
                "selected_validation_dir",
                "source_flowchart_file",
            ):
                value = str(selection.get(field) or "").strip()
                if not value:
                    continue
                path = Path(value)
                path = path if path.is_absolute() else root / path
                if not path.exists():
                    errors.append(f"{case_key}: missing {field}: {value}")

    suites = registry.get("suite_contracts", {})
    if not isinstance(suites, dict):
        errors.append("suite_contracts must be an object")
    else:
        for suite, contract in suites.items():
            if not isinstance(contract, dict):
                errors.append(f"suite_contracts.{suite} must be an object")
                continue
            actual = sum(suite in record.get("suites", []) for record in records if isinstance(record, dict))
            expected = contract.get("expected_case_count")
            if isinstance(expected, int) and actual != expected:
                errors.append(f"suite {suite}: expected {expected} cases, found {actual}")
    return errors


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def find_case(registry: dict[str, Any], case_key: str) -> dict[str, Any] | None:
    return next((record for record in case_records(registry) if record.get("case_key") == case_key), None)


def normalize_tags(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip().lower().replace(" ", "_") for value in values if str(value).strip()})
