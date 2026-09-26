"""Frozen native runner registry for the NC v5 primary suite."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunnerRegistration:
    runner_id: str
    entrypoint: str
    contract_version: str
    deterministic_solver_retries: int


RUNNERS = {
    "native_candidate_runner_v5": RunnerRegistration(
        runner_id="native_candidate_runner_v5",
        entrypoint="stage3_specs_solve.nc_v5.native_runner:run_native_candidate_v5",
        contract_version="native-candidate-runner/v5",
        deterministic_solver_retries=1,
    )
}


def resolve_runner(runner_id: str) -> RunnerRegistration:
    try:
        return RUNNERS[runner_id]
    except KeyError as exc:
        raise KeyError(f"unregistered NC v5 native runner: {runner_id}") from exc
