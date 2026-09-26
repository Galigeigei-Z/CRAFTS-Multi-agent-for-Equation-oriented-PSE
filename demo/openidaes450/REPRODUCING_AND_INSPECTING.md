# Reproducing and inspecting OpenIDAES-450 cases

## Browse the cases on GitHub

Start with the [450-case index](CASE_INDEX.md). Each case has a description, a full
specification and topology, recorded runtime versions, and its available computed
stream, unit/state-variable or optimization results. The case README links the
applicable tables, property-package configuration, solver evidence and checks.

The case's model type and solver report define how to interpret its outputs.
[Model scope and validation](MODEL_SCOPE.md) explains the result schemas,
reproduction coverage and case execution requirements.

## Reproduce a selected case

1. Download and extract the full archive from the
   [demo release](https://github.com/Galigeigei-Z/CRAFTS-Multi-agent-for-Equation-oriented-PSE/releases/tag/openidaes450-demo-2026-09-26).
   Alternatively, clone the repository and use `demo/openidaes450`. Each case
   includes `model.py` and `executable_source.py`, with shared source dependencies
   under `sources/`. Package wheels are distributed in the release archive.
2. Follow [setup and usage](SETUP_AND_USAGE.md) to choose the recorded runtime,
   install packages and configure the required solver/native libraries. Check
   external source/data bindings for the selected runner.
3. From the extracted `OpenIDAES-450-demo` directory or repository
   `demo/openidaes450` directory, run the command shown in the
   case README. Always use a new output directory. The launcher does not overwrite
   the supplied results.
4. Read the new `status.json`, `runner_report.json`, `solver_events.json` and
   `model_checks.json`, where applicable, before comparing numerical outputs.
   Preserve failures and warnings rather than substituting the supplied results.

## Inspect specifications and numerical results

| Question | Files to inspect |
|---|---|
| What process was requested? | `README.md`, `specification.json`, `topology.json` |
| What model was actually computed? | `case.json`, `runner_report.json`, `demo_assumptions.json` where present |
| Which packages/property method were used? | `environment.json` or `runtime_versions.json`, `property_packages.json`, `parameters.json` |
| What were the stream and unit values? | `streams.csv`, `unit_and_state_variables.csv`, `units.json`, where defined |
| Did the selected solve converge? | `solver_events.json`, `runner_report.json`, `status.json` |
| Are there residuals or missing values? | `model_checks.json`, `missing_values.json`, where present |

CSV files can be downloaded and opened in a spreadsheet or read with pandas.
Inspect column names and units instead of assuming all model families share one
stream schema. Match feed conditions, thermodynamic assumptions, basis, fixed
operating decisions and units before comparing simulators. Report absolute and
relative differences with explicit tolerances and coverage/exclusions.

## Reporting comparisons

Record the model scope, matching conditions, solver termination, numerical
diagnostics and comparison tolerances. The [scope document](MODEL_SCOPE.md)
identifies the reduced demonstrations, fixed-decision cases and missing-value
conventions.

If you find OpenIDAES-450 useful, please cite our paper, [CRAFTS: Collaborative Role-Adaptive Fine-Tuning of LLM Agents for Chemical Process Simulation](https://arxiv.org/abs/2608.01369), and acknowledge the IDAES project.
