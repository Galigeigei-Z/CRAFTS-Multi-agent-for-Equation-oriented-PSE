# WaterTAP BSM2 ElectroNP no bioP

`blind_synthesized_watertap_electroNP_bsm2_no_bioP`

## Description and specification

Build a WaterTAP BSM2 wastewater-treatment flowsheet with activated-sludge reactors, clarification, sludge recycle, anaerobic digestion, and ElectroNP phosphorus recovery. Use the configuration without biological phosphorus removal.

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
| `fs.props_ASM1` | `watertap.property_models.unit_specific.activated_sludge.asm1_properties.ASM1ParameterBlock` |
| `fs.props_ADM1` | `watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties.ADM1ParameterBlock` |
| `fs.props_vap` | `watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties_vapor.ADM1_vaporParameterBlock` |
| `fs.ADM1_rxn_props` | `watertap.property_models.unit_specific.anaerobic_digestion.adm1_reactions.ADM1ReactionParameterBlock` |
| `fs.ASM1_rxn_props` | `watertap.property_models.unit_specific.activated_sludge.asm1_reactions.ASM1ReactionParameterBlock` |

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
- [Shared runner and its source location](../../sources/workspace/stage3_specs_solve/run_watertap_bsm2_reference_solve.py)

`model.py` invokes the shared launcher; `executable_source.py` is the selected runner. Some runners import shared model-building modules. These dependencies are supplied under `sources/`; upstream packages, solver libraries and external data still need the documented environment.

## Reproduce and inspect

Follow the [reproduction and inspection guide](../../REPRODUCING_AND_INSPECTING.md), use this repository’s `demo/openidaes450` directory or the extracted release archive and activate the recorded compatible environment. From `demo/openidaes450` in the repository (or the extracted `OpenIDAES-450-demo` directory):

```bash
python run_case.py --case blind_synthesized_watertap_electroNP_bsm2_no_bioP --output /tmp/blind_synthesized_watertap_electroNP_bsm2_no_bioP-rerun
```

Use a new output directory. Some cases require external source/data bindings or specialized solver libraries; inspect the setup guide and selected source before running. Compare the new outputs with these selected results on matching bases and units, and retain any residual warnings.
