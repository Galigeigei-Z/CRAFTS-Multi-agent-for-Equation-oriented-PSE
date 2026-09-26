"""Runtime bootstrap for the shared py310 environment on Vanda."""

from __future__ import annotations

import os
PY310_LIB = "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
THREAD_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)


def configure_py310_runtime() -> None:
    """Normalize imports and solver runtime behavior for py310 scripts."""
    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    for name in THREAD_ENV_VARS:
        os.environ.setdefault(name, "1")

    ld_library_path = os.environ.get("LD_LIBRARY_PATH", "")
    if PY310_LIB not in ld_library_path.split(":"):
        os.environ["LD_LIBRARY_PATH"] = (
            f"{PY310_LIB}:{ld_library_path}" if ld_library_path else PY310_LIB
        )
