# Model scope and validation record

OpenIDAES-450 provides inspectable case records, source programs, configuration
exports and selected computed outputs. Use the per-case model type and execution
evidence when reproducing a calculation or comparing another simulator.

## Model families

| Model type | Cases | Interpretation |
|---|---:|---|
| Native IDAES | 237 | IDAES-based model implementations with exported configuration and available stream/unit values. |
| Original reduced models | 163 | Reduced models retained from the registered case implementations. |
| New reduced demonstrations | 11 | Explicitly scoped alternatives with recorded assumptions; they do not reproduce the original full reference model. |
| Grid optimization | 21 | Electrical planning/optimization models; conventional process stream tables may not apply. |
| Design optimization | 17 | Design-selection optimization models with their corresponding decision variables and results. |
| EXPOsan dynamic model | 1 | External dynamic simulation with its own result schema and runtime. |
| **Total** | **450** | |

All 450 entries contain selected fresh computed outputs. `fresh_completed`
identifies accepted demo execution; it does not by itself certify full-reference
convergence or physical validation. Solver termination and numerical checks remain
available in each case folder. Residual warnings were retained and were not all
used as rejection conditions for this release.

The 11 newly reduced demonstrations retain their labels and assumptions. FlexDesal
uses fixed operating decisions and nominal recovery rather than a free scheduling
optimum. METAB retains unavailable cells in its external results. A model without
Pyomo ports or IDAES unit blocks may have no conventional stream/unit table.

## Using the case records

This collection supports process-model inspection, execution and numerical
cross-checks. Select cases by their descriptions, specifications and model types.
For each comparison, record the runtime, solver, matching conditions, numerical
tolerances and available outputs. Keep reduced-model comparisons separate from
full-flowsheet validation.

## Reproduction coverage

- File and link checks cover all 450 case folders.
- Python entry points, selected runner files and bundled runner paths were checked for all 450 cases.
- The 35-wheel standard simulation environment passed offline installation and dependency checks in a fresh virtual environment; a HiGHS test solved optimally.
- One case was rerun successfully through both the packaged and repository launchers in an existing compatible environment.

These checks do not constitute clean-environment reruns of all 450 cases.
Specialized runtimes, native solver libraries and external source/data bindings
remain case-specific requirements. See the [setup guide](SETUP_AND_USAGE.md) and
`PACKAGE_CHECK.json`, `BROWSABLE_CASES_CHECK.json` and `SOLVER_SOURCE_CHECK.json`
for the available records.
