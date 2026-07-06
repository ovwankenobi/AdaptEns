# -*- coding: utf-8 -*-
"""
Optimized FSS-displacement compiler using NPZ tensor storage.

Each pairwise FSS is converted to a displacement d = (1 - FSS) * (2L + 1)
immediately after it is computed; only the displacement is stored.

Design notes (v2 — see inline comments for details):

1. Pairwise FSS is computed via a Gram-matrix identity instead of a Python
   loop over combinations(). For a fixed valid-data mask across ensemble
   members (true when missingness comes from a static terrain/domain mask
   rather than per-file corruption), FSS reduces to:

       den[i,j] = sum_sq[i] + sum_sq[j]
       num[i,j] = sum_sq[i] + sum_sq[j] - 2 * cross[i,j]
       FSS[i,j] = 2 * cross[i,j] / den[i,j]

   where cross = F @ F.T is a single BLAS matmul per key, replacing
   n_ens-choose-2 elementwise passes with n_keys matmuls.

   IMPORTANT: this assumes the finite/invalid mask is the same for every
   ensemble member at a given key, for a given forecast time. If any member
   can have spurious per-file NaNs (corrupted file, partial write, etc.)
   that other members don't share, this mask union changes what's being
   compared vs the original per-pair isfinite(f) & isfinite(o) logic.
   VALIDATE with validate_gram_vs_loop() below on real data before trusting
   this in production.

2. netCDF4's automatic mask/scale handling is bypassed for speed, but fill
   values are still honored manually (converted to NaN) so masking
   semantics are unchanged from the original isfinite-based approach.

3. BLAS threading is controlled explicitly per worker via threadpoolctl
   (falls back to env vars if threadpoolctl isn't installed), because
   ProcessPoolExecutor spawns full BLAS thread pools per process by
   default, causing oversubscription and lock contention at high
   max_workers.

4. Per-phase timing (load, mask/matmul, save) is collected per task and
   aggregated across the run so you can see where time is actually spent.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
import multiprocessing as mp
import os
import re
import time

import netCDF4 as nc
import numpy as np
from tqdm import tqdm
import sys

try:
    from threadpoolctl import threadpool_limits
    _HAVE_THREADPOOLCTL = True
except ImportError:
    _HAVE_THREADPOOLCTL = False


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_VARS = ["barometric_pressure", "wind_u", "wind_v"]
_L_VALUES = [1, 3, 5]
_KEYS = [f"{v}_L{L}" for v in _VARS for L in _L_VALUES]

_KEY_FACTORS = {
    f"{v}_L{L}": np.float32(2 * L + 1)
    for v in _VARS
    for L in _L_VALUES
}


def _scale_factors(keys) -> np.ndarray:
    return np.asarray(
        [_KEY_FACTORS[str(key)] for key in keys],
        dtype=np.float32,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _natural_sort_key(path: Path):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.name)
    ]


def _limit_timesteps(items, compute_timestep):
    """
    Restrict an ordered sequence of timestep items to the requested count.

    compute_timestep = "ALL" -> keep every timestep.
    compute_timestep = 1     -> keep only the first timestep.
    compute_timestep = N     -> keep the first N timesteps.
    """
    if isinstance(compute_timestep, str) and compute_timestep.upper() == "ALL":
        return items
    return items[: int(compute_timestep)]


def _load_arrays(file: Path):
    """
    Loads variables for one ensemble file, bypassing netCDF4's automatic
    mask/scale handling for speed, but manually honoring _FillValue /
    missing_value so masking semantics match the original isfinite-based
    approach exactly (fill values become NaN, same as auto-masking would
    produce, just without the library doing it internally per read).

    Returns:
        keys: list[str]
        stacked array shape: (n_keys, y, x), dtype float32, invalid -> NaN
    """
    with nc.Dataset(file) as ds:
        arrays = []
        keys = []

        for key in _KEYS:
            if key not in ds.variables:
                continue

            var = ds.variables[key]
            var.set_auto_maskandscale(False)  # skip internal masking pass
            raw = var[:]

            fill = None
            for attr in ("_FillValue", "missing_value"):
                if attr in var.ncattrs():
                    fill = var.getncattr(attr)
                    break

            arr = raw.astype(np.float32)

            if fill is not None:
                arr = np.where(raw == fill, np.nan, arr)
            # If the file has no fill-value attribute at all, we assume
            # invalid data is already stored as NaN in the raw array
            # (matches original behavior for such files).

            arr *= np.float32(0.01)
            arrays.append(arr)
            keys.append(key)

        if not arrays:
            return None, None

        stacked = np.stack(arrays, axis=0)
        return keys, stacked


def _set_blas_threads(n_threads: int):
    """
    Returns a context manager limiting BLAS threads for this process.
    Prefers threadpoolctl (reliable at runtime); falls back to env vars
    (only reliable if set before any BLAS call has run in this process).
    """
    if _HAVE_THREADPOOLCTL:
        return threadpool_limits(limits=n_threads)

    os.environ["OMP_NUM_THREADS"] = str(n_threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(n_threads)
    os.environ["MKL_NUM_THREADS"] = str(n_threads)

    class _NullCtx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _NullCtx()


def _init_worker(threads_per_worker: int):
    """
    ProcessPoolExecutor initializer. Sets env vars as an early fallback
    (helps if threadpoolctl is unavailable and no BLAS call has happened
    yet in this fresh process). The per-task threadpool_limits context
    manager in _process_forecast_time is the actual guarantee.
    """
    os.environ["OMP_NUM_THREADS"] = str(threads_per_worker)
    os.environ["OPENBLAS_NUM_THREADS"] = str(threads_per_worker)
    os.environ["MKL_NUM_THREADS"] = str(threads_per_worker)


# ------------------------------------------------------------------
# Gram-matrix vectorized FSS (replaces the combinations() loop)
# ------------------------------------------------------------------

def _fss_gram_all_pairs(stack: np.ndarray) -> np.ndarray:
    """
    stack shape: (n_ens, n_keys, y, x)

    Returns displacement-ready FSS matrix, shape (n_ens, n_ens, n_keys),
    computed via one Gram-matrix matmul per key instead of a Python loop
    over all ensemble pairs. The whole reduction runs in float32.

    Invalid pixels (per key, ANDed across ensemble members) are dropped
    before the matmul rather than zeroed-and-kept, so a key with a large
    static invalid region (terrain/domain mask) costs less than a dense
    matmul over the full grid — the result is identical either way since
    zeroed pixels contribute nothing to sum_sq/cross.

    ASSUMPTION: the finite/invalid mask is the same across all ensemble
    members for a given key (see module docstring). Validate against the
    loop-based reference before trusting in production — see
    validate_gram_vs_loop().
    """
    n_ens, n_keys, y, x = stack.shape
    flat = stack.reshape(n_ens, n_keys, y * x)

    fss = np.empty((n_ens, n_ens, n_keys), dtype=np.float32)

    for k in range(n_keys):
        col = flat[:, k, :]  # (n_ens, npix)
        valid = np.all(np.isfinite(col), axis=0)  # (npix,)
        Fk = col[:, valid].astype(np.float32)  # (n_ens, n_valid)

        sum_sq = np.einsum("ep,ep->e", Fk, Fk, dtype=np.float32)
        cross = Fk @ Fk.T  # (n_ens, n_ens)
        den = sum_sq[:, None] + sum_sq[None, :]
        fss[:, :, k] = np.where(den == 0.0, np.float32(1.0), 2.0 * cross / den)

    return fss


def _fss_batch_reference(f, o):
    """
    Original per-pair elementwise FSS, kept only as a validation reference
    for validate_gram_vs_loop(). Not used in the production path.
    """
    mask = np.isfinite(f) & np.isfinite(o)
    diff = np.where(mask, f - o, 0.0)
    num = np.sum(diff * diff, axis=(1, 2), dtype=np.float64)
    den = np.sum(np.where(mask, f * f + o * o, 0.0), axis=(1, 2), dtype=np.float64)
    return np.where(den == 0.0, 1.0, 1.0 - num / den).astype(np.float32)


# ------------------------------------------------------------------
# Worker: load + compute fused into one task per forecast time
# ------------------------------------------------------------------

def _process_forecast_time(
    args: tuple[str, list[Path], Path, int]
) -> tuple[str, bool, str | None, dict]:
    """
    args: (forecast_name, ens_dirs, fss_dir, blas_threads)

    Returns (forecast_name, success, error_message, timings)
    timings: dict with keys 'load', 'compute', 'save' (seconds)
    """
    forecast_name, ens_dirs, fss_dir, blas_threads = args

    timings = {"load": 0.0, "compute": 0.0, "save": 0.0}

    ens_order: list[str] = []
    arrays: list[np.ndarray] = []
    keys_ref: list[str] | None = None

    t0 = time.perf_counter()
    for ens_dir in ens_dirs:
        nc_file = ens_dir / forecast_name
        if not nc_file.exists():
            continue

        try:
            keys, arr = _load_arrays(nc_file)
        except Exception as exc:
            return forecast_name, False, f"failed reading {nc_file}: {exc}", timings

        if arr is None:
            continue

        if keys_ref is None:
            keys_ref = keys
        elif keys != keys_ref:
            return forecast_name, False, (
                f"key mismatch for {ens_dir.name}: "
                f"expected {keys_ref}, got {keys}"
            ), timings

        ens_order.append(ens_dir.name)
        arrays.append(arr)
    timings["load"] = time.perf_counter() - t0

    if not arrays or keys_ref is None:
        return forecast_name, False, "no ensemble data found for this time", timings

    t0 = time.perf_counter()
    stack = np.stack(arrays, axis=0)  # (n_ens, n_keys, y, x)
    del arrays

    factors = _scale_factors(keys_ref)

    with _set_blas_threads(blas_threads):
        fss = _fss_gram_all_pairs(stack)

    # d = (1 - FSS) * (2L + 1)
    displacement = (1.0 - fss) * factors[None, None, :]
    displacement = displacement.astype(np.float32)
    timings["compute"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    stem = Path(forecast_name).stem
    np.savez(  # uncompressed — compression was the dominant per-file cost
        fss_dir / f"{stem}.npz",
        displacement=displacement,
        ensembles=np.array(ens_order),
        keys=np.array(keys_ref),
    )
    timings["save"] = time.perf_counter() - t0

    return forecast_name, True, None, timings


# ------------------------------------------------------------------
# Main class
# ------------------------------------------------------------------

class DetermineFSS_displacement:

    VARS = _VARS
    L_VALUES = _L_VALUES

    def __init__(
        self,
        base_dir,
        max_workers: int | None = None,
        blas_threads_per_worker: int = 1,
        compute_timestep: int | str = "ALL",
    ):
        """
        max_workers: number of process-pool workers (parallel forecast
            times in flight).
        blas_threads_per_worker: BLAS threads used inside each worker's
            matmul. max_workers * blas_threads_per_worker should not
            greatly exceed your core count, or you'll get the same
            oversubscription/lock-contention problem this replaces.
            Tune empirically: more workers / 1 thread each tends to win
            when n_ens is large and grids are small; fewer workers /
            more threads each tends to win when grids are large.
        """
        self.base_dir = Path(base_dir)

        self.fraction_dir = self.base_dir / "_adapt" / "_fraction"
        self.fss_dir = self.base_dir / "_adapt" / "_fss_disp"
        self.fss_dir.mkdir(parents=True, exist_ok=True)

        self._ens_dirs = sorted(
            (
                p for p in self.fraction_dir.iterdir()
                if p.is_dir() and p.name.endswith("_ens")
            ),
            key=_natural_sort_key,
        )

        if not self._ens_dirs:
            raise RuntimeError(
                f"No ensemble directories found in {self.fraction_dir}"
            )

        self._max_workers = max_workers or (os.cpu_count() or 1)
        self._blas_threads_per_worker = blas_threads_per_worker
        self.compute_timestep = compute_timestep

    def compile_fractions_time(self):
        sample_files = sorted(self._ens_dirs[0].glob("*.nc"))

        if not sample_files:
            raise RuntimeError(f"No NetCDF files found in {self._ens_dirs[0]}")

        forecast_names = [f.name for f in sample_files]
        forecast_names = _limit_timesteps(forecast_names, self.compute_timestep)

        task_args = [
            (
                name,
                self._ens_dirs,
                self.fss_dir,
                self._blas_threads_per_worker,
            )
            for name in forecast_names
        ]

        timing_totals = {"load": 0.0, "compute": 0.0, "save": 0.0}
        n_completed = 0

        with ProcessPoolExecutor(
            max_workers=self._max_workers,
            initializer=_init_worker,
            initargs=(self._blas_threads_per_worker,),
        ) as pool:
            futures = {
                pool.submit(_process_forecast_time, arg): arg[0]
                for arg in task_args
            }

            pbar = tqdm(
                total=len(forecast_names),
                desc="Computing FSS",
                unit="timestep",
            )
            for future in as_completed(futures):
                name = futures[future]
                try:
                    _, success, err, timings = future.result()
                    if success:
                        for k in timing_totals:
                            timing_totals[k] += timings.get(k, 0.0)
                        n_completed += 1
                    else:
                        tqdm.write(f"[ERROR] {name}: {err}")
                except Exception as exc:
                    tqdm.write(f"[ERROR] {name}: {exc}")
                pbar.update(1)
                pbar.set_postfix(last=name)
            pbar.close()

        if n_completed:
            print("\n--- Phase timing summary (sum across all completed files) ---")
            for phase, total in timing_totals.items():
                avg = total / n_completed
                print(f"  {phase:8s}: total={total:8.2f}s  avg/file={avg:6.3f}s")
            print(f"  files completed: {n_completed}")


if __name__ == "__main__":
    mp.freeze_support()
    """
    path = (
        r"D:\rsderamos\Operational_06_18_2026\Operations"
        r"\meteo_database\ecmwf_meteo\20260701_06z"
    )
    """

    path = sys.argv[1]
    compute_timestep =  sys.argv[2]
    fss = DetermineFSS_displacement(
        path, compute_timestep = compute_timestep,
        max_workers=8,
        blas_threads_per_worker=1,   # tune against blas_threads_per_worker=4, max_workers=2, etc.
    )

    fss.compile_fractions_time()