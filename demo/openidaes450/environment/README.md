# Environment packages

See [the detailed guide](../SETUP_AND_USAGE.md) for setup and usage.

- `wheelhouse/`: 35 pinned standard simulation wheels (CPython 3.10 / Linux x86-64), including their dependency closure.
- `simulation-wheels.lock`: version-pinned standard wheel installation requirements.
- `native_runtime_v5/wheelhouse/`: four original domain wheels. Domain transitive dependencies are not all bundled.
- `runtimes/`: full installed package inventories for five local runtimes, plus Conda native package records where present. These are observed inventories, not universally installable locks.
- `wheel_manifest.json`, `WHEELHOUSE_STATUS.json`: package identity and completeness information.
- `check_environment.py`: import/version report and optional tiny IPOPT/HiGHS solves.

Solver executables, IDAES extension libraries and complete specialized runtime dependencies are not bundled. Per-case runtime files identify versions used for selected results; broad runtime inventories were captured during preparation. The legacy v5 lock contains unrelated agent/GPU packages and is not the recommended default install.
