# Native runtime v5

This isolated runtime is rebuilt from a version-pinned index dependency set and
the content-addressed domain wheels bound in `domain_wheel_binding.json`.
Unlike v3, it declares `pytest` as a runtime dependency because the frozen
PrOMMiS package imports `prommis.util`, which imports pytest during native
construction. The environment uses no system site packages.

`highspy` is pinned explicitly because the fixed-450 generic ChE conservation
adapter and its optimization branch solve fresh Pyomo LPs with HiGHS. Solver
availability is part of the compute-node preflight and may not be inherited
from a user or system site-packages directory.

`NREL-PySAM` is pinned explicitly because the frozen DISPATCHES unit-model
package imports its wind-power module while constructing the nuclear
double-loop reference case. Qualification must exercise this dependency from
the v5 virtual environment rather than inherit it from the wider base Python.

`venv/` is a disposable cache. Eligibility comes from the lock, wheel binding,
exact interpreter audit, transitive import ledger, and fixed-denominator construction and
solve qualification.
