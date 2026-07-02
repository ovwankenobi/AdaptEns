# -*- coding: utf-8 -*-
"""
Optimized FSS compiler using NPZ tensor storage.

Key change vs. the original: loading and FSS computation are fused into a
single per-forecast-time worker task. Each worker reads its own ensemble
files directly from disk and computes FSS in-process, so no array data is
ever pickled between processes. The original two-pass design (load in pool
-> ship arrays back to main -> ship arrays back out to a second pool) meant
every array crossed process boundaries via IPC twice and the main process
had to hold the entire dataset (all timesteps x all ensembles) in memory
simultaneously. This version never materializes that full in-memory copy.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path
import multiprocessing as mp
import os
import re

import netCDF4 as nc
import numpy as np
from tqdm import tqdm


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_VARS = ["barometric_pressure", "wind_u", "wind_v"]
_L_VALUES = [1, 3, 5]
_KEYS = [f"{v}_L{L}" for v in _VARS for L in _L_VALUES]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _natural_sort_key(path: Path):
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.name)
    ]


def _load_arrays(file: Path):
    """
    Returns:
        keys: list[str]
        stacked array shape: (n_keys, y, x)
    """
    with nc.Dataset(file) as ds:
        arrays = []
        keys = []

        for key in _KEYS:
            if key in ds.variables:
                arr = ds.variables[key][:].astype(np.float32)
                arr *= np.float32(0.01)
                arrays.append(arr)
                keys.append(key)

        if not arrays:
            return None, None

        stacked = np.stack(arrays, axis=0)
        return keys, stacked


# ------------------------------------------------------------------
# Vectorized FSS
# ------------------------------------------------------------------

def _fss_batch(f, o):
    """
    f/o shape:
        (n_keys, y, x)

    returns:
        (n_keys,)
    """
    mask = np.isfinite(f) & np.isfinite(o)

    diff = np.where(mask, f - o, 0.0)

    num = np.sum(
        diff * diff,
        axis=(1, 2),
        dtype=np.float64
    )

    den = np.sum(
        np.where(mask, f * f + o * o, 0.0),
        axis=(1, 2),
        dtype=np.float64
    )

    return np.where(
        den == 0.0,
        1.0,
        1.0 - num / den
    ).astype(np.float32)


# ------------------------------------------------------------------
# Worker: load + compute fused into one task per forecast time
# ------------------------------------------------------------------

def _process_forecast_time(
    args: tuple[str, list[Path], Path]
) -> tuple[str, bool, str | None]:
    """
    Worker process: for a single forecast time step, load every ensemble's
    NetCDF file for that time step and compute the pairwise FSS matrix.

    args: (forecast_name, ens_dirs, fss_dir)

    Returns (forecast_name, success, error_message)
    """
    forecast_name, ens_dirs, fss_dir = args

    ens_order: list[str] = []
    arrays: list[np.ndarray] = []
    keys_ref: list[str] | None = None

    for ens_dir in ens_dirs:
        nc_file = ens_dir / forecast_name
        if not nc_file.exists():
            continue

        try:
            keys, arr = _load_arrays(nc_file)
        except Exception as exc:
            return forecast_name, False, f"failed reading {nc_file}: {exc}"

        if arr is None:
            continue

        if keys_ref is None:
            keys_ref = keys
        elif keys != keys_ref:
            # Variable set differs from the reference ensemble for this
            # time step; skip rather than silently misaligning tensors.
            return forecast_name, False, (
                f"key mismatch for {ens_dir.name}: "
                f"expected {keys_ref}, got {keys}"
            )

        ens_order.append(ens_dir.name)
        arrays.append(arr)

    if not arrays or keys_ref is None:
        return forecast_name, False, "no ensemble data found for this time"

    n_ens = len(arrays)
    n_keys = len(keys_ref)

    # (n_ens, n_keys, y, x)
    stack = np.stack(arrays, axis=0)
    del arrays  # release references; stack owns the data now

    scores = np.full(
        (n_ens, n_ens, n_keys),
        np.nan,
        dtype=np.float32
    )

    diag = np.arange(n_ens)
    scores[diag, diag, :] = 1.0

    for i, j in combinations(range(n_ens), 2):
        pair_scores = _fss_batch(stack[i], stack[j])
        scores[i, j, :] = pair_scores
        scores[j, i, :] = pair_scores

    stem = Path(forecast_name).stem

    np.savez_compressed(
        fss_dir / f"{stem}.npz",
        scores=scores,
        ensembles=np.array(ens_order),
        keys=np.array(keys_ref),
    )

    return forecast_name, True, None


# ------------------------------------------------------------------
# Main class
# ------------------------------------------------------------------

class DetermineFSS:

    VARS = _VARS
    L_VALUES = _L_VALUES

    def __init__(self, base_dir, max_workers=None):
        self.base_dir = Path(base_dir)

        self.fraction_dir = (
            self.base_dir / "_adapt" / "_fraction"
        )

        self.fss_dir = (
            self.base_dir / "_adapt" / "_fss"
        )

        self.fss_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self._ens_dirs = sorted(
            (
                p for p in self.fraction_dir.iterdir()
                if p.is_dir() and p.name.endswith("_ens")
            ),
            key=_natural_sort_key,
        )

        if not self._ens_dirs:
            raise RuntimeError(
                f"No ensemble directories found in "
                f"{self.fraction_dir}"
            )

        # Each task now does one file-read pass per ensemble followed by
        # CPU-bound FSS math, i.e. it's a mix of I/O and CPU work rather
        # than purely I/O bound, so cpu_count() (not 2x) is a saner default.
        # Override via max_workers= if your storage is slow/networked and
        # you want more concurrent readers.
        self._max_workers = max_workers or (os.cpu_count() or 1)

    def compile_fractions_time(self):
        sample_files = sorted(
            self._ens_dirs[0].glob("*.nc")
        )

        if not sample_files:
            raise RuntimeError(
                f"No NetCDF files found in "
                f"{self._ens_dirs[0]}"
            )

        forecast_names = [f.name for f in sample_files]

        task_args = [
            (name, self._ens_dirs, self.fss_dir)
            for name in forecast_names
        ]

        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
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
                    _, success, err = future.result()
                    if not success:
                        tqdm.write(f"[ERROR] {name}: {err}")
                except Exception as exc:
                    tqdm.write(f"[ERROR] {name}: {exc}")
                pbar.update(1)
                pbar.set_postfix(last=name)
            pbar.close()


# ------------------------------------------------------------------
# Reader helper
# ------------------------------------------------------------------

def load_fss(npz_file):
    data = np.load(npz_file, allow_pickle=False)

    scores = data["scores"]
    ensembles = data["ensembles"]
    keys = data["keys"]

    return scores, ensembles, keys


if __name__ == "__main__":
    mp.freeze_support()

    path = (
        r"D:\rsderamos\Operational_06_18_2026\Operations"
        r"\meteo_database\ecmwf_meteo\20260621_00z"
    )

    fss = DetermineFSS(path, max_workers=8)
    fss.compile_fractions_time()