# PrOMMiS UKy Flowsheet

`blind_synthesized_prommis_uky_flowsheet`

## Description and specification

Build the full PrOMMiS UKy rare-earth recovery flowsheet with leaching, solid-liquid separation, rougher loading, scrubbing and stripping, cleaner extraction, precipitation, roasting, purge streams, and a rare-earth-oxide product.

[Full specification](specification.json) · [Topology](topology.json) · [Case metadata](case.json)

## Selected computation

- Model type: `native_IDAES`
- Execution status: `fresh_completed`
- Solver result: `optimal` — [solver summary](solver_summary.json)

Consult the original specification, executable source in the release archive, and solver evidence for the implemented scope.

## Solver and property metadata

[Solver status and termination evidence](solver_summary.json) · [Property-package identity summary](property_summary.json)

| Model component | Property/reaction package class |
|---|---|
| `fs.leach_soln` | `prommis.properties.sulfuric_acid_leaching_properties.SulfuricAcidLeachingParameters` |
| `fs.coal` | `prommis.properties.coal_refuse_properties.CoalRefuseParameters` |
| `fs.HCl_stripping_params` | `prommis.properties.hcl_stripping_properties.HClStrippingParameterBlock` |
| `fs.prop_o` | `prommis.solvent_extraction.ree_og_distribution.REESolExOgParameters` |
| `fs.properties_solid` | `prommis.precipitate.precipitate_solids_properties.PrecipitateParameters` |
| `fs.prop_gas` | `idaes.models.properties.modular_properties.base.generic_property.GenericParameterBlock` |
| `fs.prop_solid` | `prommis.precipitate.precipitate_solids_properties.PrecipitateParameters` |

Configuration and thermodynamic options are recorded in [property_packages.json](property_packages.json).

## Results and configuration

The files below contain the selected computed outputs and execution evidence. Empty or unavailable fields are preserved. Models without process-stream ports or IDAES unit blocks do not provide conventional stream/unit tables. The solver report records convergence for the implemented model.

- [Stream results](streams.csv)
- [Unit and state variable results](unit_and_state_variables.csv)
- [Unit-model configuration](units.json)
- [Property-package configuration](property_packages.json)
- [Model parameters](parameters.json)
- [Connections](arcs.json)
- [Runtime environment](environment.json)
- [Computation report and scope](runner_report.json)
- [Solver termination and options](solver_events.json)
- [Residual and missing-value checks](model_checks.json)
- [Execution status](status.json)

## Python solver and model programs

- [executable_source.py](executable_source.py)
- [model.py](model.py)
- [Shared runner and its source location](../../sources/workspace/stage3_specs_solve/run_prommis_uky_reference_solve.py)

`model.py` invokes the shared launcher; `executable_source.py` is the selected runner. Some runners import shared model-building modules. These dependencies are supplied under `sources/`; upstream packages, solver libraries and external data still need the documented environment.

## Reproduce and inspect

Follow the [reproduction and inspection guide](../../REPRODUCING_AND_INSPECTING.md), use this repository’s `demo/openidaes450` directory or the extracted release archive and activate the recorded compatible environment. From `demo/openidaes450` in the repository (or the extracted `OpenIDAES-450-demo` directory):

```bash
python run_case.py --case blind_synthesized_prommis_uky_flowsheet --output /tmp/blind_synthesized_prommis_uky_flowsheet-rerun
```

Use a new output directory. Some cases require external source/data bindings or specialized solver libraries; inspect the setup guide and selected source before running. Compare the new outputs with these selected results on matching bases and units, and retain any residual warnings.
