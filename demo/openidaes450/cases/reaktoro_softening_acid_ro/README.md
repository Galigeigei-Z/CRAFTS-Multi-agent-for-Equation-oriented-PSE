# Reaktoro-PSE Softening-Acid-RO Train

`reaktoro_softening_acid_ro`

## Description and specification

Build the Reaktoro-PSE treatment train coupling chemical softening acid dosing and reverse osmosis with equilibrium chemistry and process costing.

[Full specification](specification.json) · [Topology](topology.json) · [Case metadata](case.json)

## Selected computation

- Model type: `new_reduced_demo`
- Execution status: `fresh_completed`
- Solver result: `optimal` — [solver summary](solver_summary.json)

Component-conserving softening/RO/MD/crystallization split model; fixed recoveries, ideal salt rejection, no equilibrium speciation or detailed membrane model.

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
python run_case.py --case reaktoro_softening_acid_ro --output /tmp/reaktoro_softening_acid_ro-rerun
```

Use a new output directory. Some cases require external source/data bindings or specialized solver libraries; inspect the setup guide and selected source before running. Compare the new outputs with these selected results on matching bases and units, and retain any residual warnings.
