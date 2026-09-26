# Setup, packages and use

## 1. What this archive contains

Open `index.html` locally to search all 450 cases; browsing needs no Python or solver. `catalog.csv`, `catalog.json` and `SUMMARY.json` provide machine-readable inventories. The package links each case to its source, configuration, runtime and selected
computed outputs. See [model scope and validation](MODEL_SCOPE.md) for the model
families, solver-evidence interpretation and case execution requirements.

## 2. Choose the runtime from evidence

`environment/case_runtime_index.csv` maps all 450 cases to their recorded Python/IDAES/Pyomo versions and a suggested inventory. This is a convenience mapping; check the case record before selecting an environment.

Start with the case's `environment.json` or `runtime_versions.json`, not its name. A reduced demonstration of a Reaktoro or REFLO process can use the standard runtime.

| Runtime inventory | Purpose | How to interpret it |
|---|---|---|
| `environment/runtimes/standard/` | Python 3.10 / IDAES / Pyomo, most selected runs | `simulation-requirements.txt` is a smaller dependency closure for simulation; `observed-packages.txt` is the full installed inventory. |
| `environment/runtimes/reaktoro/` | Specialized Reaktoro runs | Python 3.12; native Reaktoro libraries and separate IDAES/Pyomo versions. |
| `environment/runtimes/metab/` | EXPOsan / QSDsan / BioSTEAM | Python 3.10; IDAES and Pyomo are not used by the METAB computation. |
| `environment/runtimes/reflo/`, `bped/` | Additional installed support environments | Captured for reference; their presence does not prove a selected case used them. |

Inventories were captured during demo preparation. Per-case records are the evidence for the selected run. An installed-package inventory is not a portable pip lock: native/Conda packages, locally built versions and source dependencies may need separate installation. `conda-packages.json` records native package versions/builds when present. Do not merge all five inventories into one environment.

## 3. Standard simulation setup

Use Linux x86-64 and CPython 3.10 for the provided standard binary wheels. Other platforms need matching builds. Work from the extracted demo root. The following creates a new environment without modifying an existing one:

```bash
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --find-links environment/wheelhouse \
  -r environment/simulation-wheels.lock
python -m pip check
```

Check `environment/WHEELHOUSE_STATUS.json` first: the offline command is usable only when the standard closure is complete. If unavailable for your platform, use the same requirements with your approved package index (omit `--no-index --find-links ...`). The four original domain wheels are in `environment/native_runtime_v5/wheelhouse/`. Install a domain wheel only when the chosen case needs it. For example:

```bash
python -m pip install environment/native_runtime_v5/wheelhouse/watertap-1.7.dev0-py3-none-any.whl
python -m pip check
```

This domain installation may download further dependencies. The full `native_runtime_v5/requirements.lock` is an older broad agent-runtime lock with GPU/LLM packages; it is not the default simulation installer. `domain-wheels.lock` lists the four domain wheels when run from `environment/`, but `--no-deps` does not install their dependencies.

## 4. Configure and verify solvers

Python wheels do not include every required solver executable or native library. Nonlinear IDAES/WaterTAP models generally need IPOPT and may need IDAES extension libraries (for example cubic-root or Helmholtz functions). Install compatible IDAES extensions using the installed CLI; inspect `idaes get-extensions --help` and select a build compatible with your OS. The standard runs recorded IPOPT 3.13.2; another solver build may produce different results. Use that version/build where exact reproduction matters. Extension downloads require network access.

Linear scheduling/grid problems may use HiGHS through `highspy` / `appsi_highs`. A case that requests another solver still needs that solver and any required license. See its executable source and `solver_events.json` for the actual solver class and options. Record solver changes when comparing a rerun with the supplied results.

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
python environment/check_environment.py --solve
```

The probe solves one tiny IPOPT problem and one tiny HiGHS problem. Both must report `optimal: true` for the combined probe to pass. It checks basic solver operation, not every flowsheet or native extension. If a shared library is missing, configure the library path for your own installation; do not copy an absolute `/scratch/...` path from the development host.

## 5. Specialized environments

Keep Reaktoro separate from the Python 3.10 standard environment. Use its recorded Python version, native Conda package inventory and Python inventory to reconstruct a compatible environment; verify `import reaktoro`, IDAES and Pyomo. Pip alone may not reconstruct native Reaktoro dependencies. The inventory records the observed builds, but no clean-install reconstruction of this environment was performed for this archive.

METAB requires the recorded EXPOsan/QSDsan/BioSTEAM versions and upstream METAB source/data. Its runner currently contains a site-specific source binding; `original_model_source.py` records the selected source where available. Adapt the binding to your local source checkout before running elsewhere. `--workspace` supports original-workspace use but does not rewrite arbitrary absolute paths inside upstream source files. Other domain runners can have similar external requirements.

Use `python environment/check_environment.py` (without `--solve`) for a package inventory in a specialized environment. Missing IDAES/Pyomo is expected for METAB. Do not interpret the absence of an IDAES property package as a missing thermodynamic result for a model that does not use IDAES.

## 6. Run one case

Run from the demo root with the appropriate environment activated:

```bash
python run_case.py \
  --case variant_watertap_ro_antiscalant_recycle_purge \
  --output /tmp/openidaes-ro-run
# Equivalent entry point:
python cases/variant_watertap_ro_antiscalant_recycle_purge/model.py \
  --output /tmp/openidaes-ro-run-2
```

The output directory must not already exist. Supplied reference results are never overwritten. The launcher limits common numerical libraries to one thread. To use another interpreter, supply `--python /path/to/environment/bin/python`. When site-specific dependencies require the original workspace, add `--workspace /path/to/workspace`. External files still need to exist at the paths expected by the selected source.

Begin with one case. For parallel runs, use separate output directories and a small worker count allowed by your machine or cluster policy. Heavy dynamic models can use substantial CPU and memory. Use the cluster scheduler when required; do not launch all 450 jobs on a shared login node.

## 7. Read and compare outputs

| File | Meaning |
|---|---|
| `specification.json`, `topology.json` | Original case inputs and topology; interpret them with the implemented scope in `case.json` and the runner report. |
| `environment.json`, `runtime_versions.json` | Recorded versions for selected computation. |
| `property_packages.json`, `property_summary.json`, `parameters.json` | Explicit package class/module, thermodynamic configuration and parameters, where defined. |
| `streams.csv`, `unit_and_state_variables.csv` | Actual available stream/variable values. Inspect names and units before mapping between simulators. |
| `units.json`, `arcs.json` | Model units and connections where the implementation defines them. |
| `solver_summary.json`, `runner_report.json`, `solver_events.json`, `status.json` | Solver result, termination, source of evidence and model scope. |
| `model_checks.json` | Residuals, unavailable values and diagnostics. Warnings were not all treated as rejection conditions for this demo. |
| `external_stream_results.csv`, `missing_values.json` | METAB external results and retained unavailable cells. |

Empty stream/property tables may mean the model has no Pyomo ports or IDAES property package. METAB has unavailable cells that remain blank. For independent cross-checks, match feed conditions, basis, units, property method, fixed decisions and boundary conditions; compare absolute and relative errors with stated tolerances. Report coverage and exclusions. A reduced model is not an independent full-flowsheet reference.


## 8. Troubleshooting and verification

- `ModuleNotFoundError`: confirm the selected Python environment, install the corresponding dependency, and check source bindings. Use the top-level launcher so bundled imports are configured.
- Solver unavailable / missing shared library: run the solver probe; verify executable and native-library paths separately from Python imports.
- File not found under `/scratch/`: an upstream source/data binding still needs relocation or the original workspace. The archive does not claim complete portable dependency closure.
- Infeasible/non-optimal solve: preserve the log and status, check inputs and solver versions, and use the solver termination record to assess convergence.
- Existing output directory: choose a new directory instead of overwriting supplied evidence.

`PACKAGE_CHECK.json` records the 450-case file/link checks and one packaged-launcher smoke test in an existing compatible environment. Environment package checks and wheel inventories are under `environment/`. The 35-wheel standard closure was installed offline into a fresh virtual environment, `pip check` passed, and a tiny HiGHS LP solved optimally; see `environment/OFFLINE_INSTALL_CHECK.json`. These are not a clean-install test of all 450 cases or the specialized runtimes.

If you find OpenIDAES-450 useful, please cite our paper, [CRAFTS: Collaborative Role-Adaptive Fine-Tuning of LLM Agents for Chemical Process Simulation](https://arxiv.org/abs/2608.01369), and acknowledge the IDAES project.

## Solver and property records

Each case includes `solver_summary.json` and `property_summary.json`. An exact solver termination enum is shown when it was recorded. Older runs that retained only optimality checks are labeled `optimality_confirmed`, without inventing an exact enum; new executions record both. The BTX Flash Canary, FeedFlash Unit and HDA Once-Through Single Flash were rerun and have exact `optimal` termination records. `property_packages.json` identifies every exported parameter package by class and module, with the original configuration. Models without IDAES parameter packages have an explicit applicability record.
