#!/usr/bin/env python3
"""Bind ChE adapter declarations to the exact specification lookups in source."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_SOURCE = ROOT / "sandbox_solver" / "solve_build_plan.py"


def _numeric(node: ast.AST) -> float | bool | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        value = None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _numeric(node.operand)
        if isinstance(operand, (int, float)) and not isinstance(operand, bool):
            return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp):
        left, right = _numeric(node.left), _numeric(node.right)
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in (left, right)):
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
    return None


def _literal_key(target: ast.AST, variable: ast.AST) -> tuple[str, str] | None:
    try:
        values = ast.literal_eval(target), ast.literal_eval(variable)
    except (ValueError, TypeError):
        return None
    if all(isinstance(value, str) and value for value in values):
        return values
    return None


def _function_index(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function_lookups(
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef],
) -> tuple[dict[tuple[str, str], list[float | bool]], list[set[tuple[str, str]]], list[str]]:
    direct: dict[tuple[str, str], list[float | bool]] = {}
    alternatives: list[set[tuple[str, str]]] = []
    dynamic: list[str] = []
    for function in functions:
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            name = call.func.id if isinstance(call.func, ast.Name) else ""
            if name in {"_spec_value", "_spec_bool"}:
                if len(call.args) < 4:
                    dynamic.append(f"{function.name}:{getattr(call, 'lineno', 0)}:arity")
                    continue
                key = _literal_key(call.args[1], call.args[2])
                if key is None:
                    dynamic.append(f"{function.name}:{getattr(call, 'lineno', 0)}:dynamic_key")
                    continue
                default = _numeric(call.args[3])
                direct.setdefault(key, [])
                if default is not None:
                    direct[key].append(default)
            elif name == "_spec_value_any":
                if len(call.args) < 3:
                    dynamic.append(f"{function.name}:{getattr(call, 'lineno', 0)}:arity")
                    continue
                try:
                    packed = ast.literal_eval(call.args[1])
                    group = {
                        (str(row[0]), str(row[1]))
                        for row in packed
                        if isinstance(row, tuple)
                        and len(row) == 2
                        and all(isinstance(item, str) and item for item in row)
                    }
                except (ValueError, TypeError):
                    group = set()
                if not group:
                    dynamic.append(f"{function.name}:{getattr(call, 'lineno', 0)}:dynamic_alternatives")
                    continue
                alternatives.append(group)
                default = _numeric(call.args[2])
                if default is not None:
                    for key in group:
                        direct.setdefault(key, []).append(default)
    return direct, alternatives, dynamic


def _same_value(observed: Any, expected: float | bool) -> bool:
    if isinstance(expected, bool):
        return observed is expected
    return (
        isinstance(observed, (int, float))
        and not isinstance(observed, bool)
        and math.isclose(float(observed), float(expected), rel_tol=1e-12, abs_tol=1e-15)
    )


def audit_declaration_source(
    contract_id: str,
    declaration: dict[str, Any],
    *,
    source_path: Path = IMPLEMENTATION_SOURCE,
) -> dict[str, Any]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    index = _function_index(tree)
    requested_functions = declaration.get("implementation_functions")
    requested_functions = requested_functions if isinstance(requested_functions, list) else []
    names = [str(name) for name in requested_functions if isinstance(name, str) and name]
    selected = [index[name] for name in names if name in index]
    solver_name = str(declaration.get("solver_function") or "")
    solver = index.get(solver_name) if solver_name else None
    solver_calls = {
        call.func.id
        for call in ast.walk(solver)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    } if solver is not None else set()
    direct, alternatives, dynamic = _function_lookups(selected)
    rows = declaration.get("specs") if isinstance(declaration.get("specs"), list) else []
    declared_values = {
        (str(row[0]), str(row[1])): row[2]
        for row in rows
        if isinstance(row, list) and len(row) == 4
    }
    declared = set(declared_values)
    alternative_union = set().union(*alternatives) if alternatives else set()
    required_direct = set(direct) - alternative_union
    selected_alternatives = [declared & group for group in alternatives]
    allowed = required_direct | set().union(*selected_alternatives) if selected_alternatives else required_direct
    value_mismatches: list[list[Any]] = []
    for key in sorted(declared):
        defaults = direct.get(key, [])
        if defaults and not all(_same_value(declared_values[key], default) for default in defaults):
            value_mismatches.append([key[0], key[1], declared_values[key], defaults])
    checks = {
        "implementation_functions_declared": bool(names),
        "implementation_functions_exist": bool(names) and len(selected) == len(names),
        "no_dynamic_specification_keys": not dynamic,
        "all_direct_source_lookups_declared": required_direct <= declared,
        "one_key_selected_per_alias_group": all(len(group) == 1 for group in selected_alternatives),
        "no_declaration_keys_outside_source": declared == allowed,
        "literal_defaults_match_declaration": not value_mismatches,
        "solver_function_exists_when_declared": not solver_name or solver is not None,
        "solver_calls_declared_specification_functions": not solver_name
        or (solver is not None and set(names) <= solver_calls),
    }
    return {
        "contract_id": contract_id,
        "implementation_functions": names,
        "solver_function": solver_name or None,
        "solver_calls": sorted(solver_calls),
        "source_lookup_keys": [list(key) for key in sorted(set(direct))],
        "required_direct_keys": [list(key) for key in sorted(required_direct)],
        "alternative_key_groups": [
            [list(key) for key in sorted(group)] for group in alternatives
        ],
        "dynamic_lookups": dynamic,
        "value_mismatches": value_mismatches,
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
    }


def audit_registry_source_closure(registry: dict[str, Any]) -> dict[str, Any]:
    contracts = registry.get("contracts") if isinstance(registry.get("contracts"), dict) else {}
    rows = [
        audit_declaration_source(contract_id, declaration)
        for contract_id, declaration in sorted(contracts.items())
        if isinstance(declaration, dict)
    ]
    return {
        "schema_version": "che-contract-source-closure/1",
        "implementation_source": str(IMPLEMENTATION_SOURCE.resolve()),
        "implementation_source_sha256": hashlib.sha256(IMPLEMENTATION_SOURCE.read_bytes()).hexdigest(),
        "contract_count": len(rows),
        "passed_contract_count": sum(row["passed"] for row in rows),
        "passed": bool(rows) and all(row["passed"] for row in rows),
        "contracts": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = audit_registry_source_closure(registry)
    report["registry_path"] = str(args.registry.resolve())
    report["registry_sha256"] = hashlib.sha256(args.registry.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "passed_contract_count": report["passed_contract_count"],
                "contract_count": report["contract_count"],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
