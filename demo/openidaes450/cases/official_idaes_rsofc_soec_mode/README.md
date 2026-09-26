# Official IDAES Reversible SOFC in SOEC Mode

`official_idaes_rsofc_soec_mode`

## Description and specification

Build the official IDAES reversible solid-oxide-cell plant in SOEC mode with auxiliary boiler steam generation, air and fuel-side preparation, recycle, hydrogen compression, ASU and oxycombustion integration, HRSG heat recovery, condensation, and CO2 processing.

[Full specification](specification.json) · [Topology](topology.json) · [Case metadata](case.json)

## Selected computation

- Model type: `new_reduced_demo`
- Execution status: `fresh_completed`
- Solver result: `optimal` — [solver summary](solver_summary.json)

Stoichiometric steam electrolysis and Faraday-law power balance at fixed voltage; no cell transport or integrated heat recovery model.

This case uses a newly reduced model. Its recorded assumptions define the comparison scope; see the [model scope guide](../../MODEL_SCOPE.md).

## Solver and property metadata

[Solver status and termination evidence](solver_summary.json) · [Property-package identity summary](property_summary.json)

This model does not define IDAES parameter packages; see the applicability record for its model-specific configuration.

## Results and configuration

The files below contain the selected computed outputs and execution evidence. Empty or unavailable fields are preserved. Models without process-stream ports or IDAES unit blocks do not provide conventional stream/unit tables. The solver report records convergence for the implemented model.

- [Stream results](streams.csv)
- [Unit and state variable results](unit_and_state_variables.csv)
- [Unit-model configuration](units.json)
- [Property-package configuration](property_packages.json)
- [Model parameters](parameters.json)
- [Connections](arcs.json)
- [Runtime environment](environment.json)
- [Runtime versions](runtime_versions.json)
- [Computation report and scope](runner_report.json)
- [Solver termination and options](solver_events.json)
- [Residual and missing-value checks](model_checks.json)
- [Execution status](status.json)
- [Reduced-model assumptions](demo_assumptions.json)

## Python solver and model programs

- [executable_source.py](executable_source.py)
- [model.py](model.py)
- [Shared runner and its source location](../../sources/workspace/release/openidaes450_executable/scripts_finish/reduced_demo.py)

`model.py` invokes the shared launcher; `executable_source.py` is the selected runner. Some runners import shared model-building modules. These dependencies are supplied under `sources/`; upstream packages, solver libraries and external data still need the documented environment.

## Reproduce and inspect

Follow the [reproduction and inspection guide](../../REPRODUCING_AND_INSPECTING.md), use this repository’s `demo/openidaes450` directory or the extracted release archive and activate the recorded compatible environment. From `demo/openidaes450` in the repository (or the extracted `OpenIDAES-450-demo` directory):

```bash
python run_case.py --case official_idaes_rsofc_soec_mode --output /tmp/official_idaes_rsofc_soec_mode-rerun
```

Use a new output directory. Some cases require external source/data bindings or specialized solver libraries; inspect the setup guide and selected source before running. Compare the new outputs with these selected results on matching bases and units, and retain any residual warnings.
