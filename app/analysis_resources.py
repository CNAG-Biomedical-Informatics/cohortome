"""Fixed single-thread policy for analysis child processes."""
import os


THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OMP_THREAD_LIMIT": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "GOTO_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "NUMEXPR_MAX_THREADS": "1",
    "RCPP_PARALLEL_NUM_THREADS": "1",
    "R_DATATABLE_NUM_THREADS": "1",
    "MC_CORES": "1",
}


def single_thread_environment():
    # Override inherited workstation defaults without changing the web process.
    return {**os.environ, **THREAD_ENV}
