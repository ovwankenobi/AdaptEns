# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import permutations
from pathlib import Path
import json
import os
import re

import numpy as np
import xarray as xr
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Module-level FSS worker (must be top-level for multiprocessing pickling)
# ---------------------------------------------------------------------------

_VARS = ["barometric_pressure", "wind_u", "wind_v"]
_L_VALUES = [1, 3, 5]
_KEYS = [f"{v}_L{L}" for v in _VARS for L in _L_VALUES]


def _natural_sort_key(path: Path) -> list:
    """
    Sort '1_ens', '2_ens' ... '10_ens', '11_ens' numerically,
    not lexicographically (which would give 1, 10, 11, 2, ...).
    """
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.name)
    ]


def _load_arrays(file: Path) -> dict[str, np.ndarray]:
    """
    Open one NetCDF file and extract all FSS keys as float32 arrays.
    Returns only the keys that are actually present.
    Prints a warning if none of the expected keys are found.
    """
    with xr.open_dataset(file) as ds:
        found = {
            key: ds[key].values.astype(np.float32) * np.float32(0.01)
            for key in _KEYS
            if key in ds.variables
        }
        if not found:
            available = list(ds.variables)
            tqdm.write(
                f"[WARN] No expected keys found in {file}\n"
                f"       Expected : {_KEYS}\n"
                f"       Available: {available}"
            )
        return found


def _fss_from_arrays(
    f: np.ndarray,
    o: np.ndarray,
) -> float:
    """Compute FSS for a single pre-loaded array pair."""
    mask = np.isfinite(f) & np.isfinite(o)
    if not mask.any():
        return float("nan")

    f, o = f[mask], o[mask]
    numerator = np.sum((f - o) ** 2, dtype=np.float64)
    denominator = np.sum(f ** 2 + o ** 2, dtype=np.float64)

    return 1.0 if denominator == 0.0 else float(1.0 - numerator / denominator)


def _process_forecast_file(
    forecast_name: str,
    ens_dirs: list[Path],
    fss_dir: Path,
) -> str:
    """
    Worker function: loads every ensemble file for one forecast time,
    computes all pairwise FSS scores, and writes the JSON result.
    Designed to run in a subprocess.
    """
    # --- load all arrays once per ensemble ---
    cache: dict[str, dict[str, np.ndarray]] = {}
    for ens_dir in ens_dirs:
        nc_file = ens_dir / forecast_name
        if nc_file.exists():
            cache[ens_dir.name] = _load_arrays(nc_file)

    # --- compute pairwise FSS ---
    # Preserve natural order in output by iterating ens_dirs order
    ens_order = [d.name for d in ens_dirs if d.name in cache]
    output: dict[str, list] = {name: [] for name in ens_order}
    shared_keys_cache: dict[tuple[str, str], list[str]] = {}

    for ind_name, dep_name in permutations(ens_order, 2):
        ind_arrays = cache[ind_name]
        dep_arrays = cache[dep_name]

        pair = (ind_name, dep_name)
        if pair not in shared_keys_cache:
            shared_keys_cache[pair] = [
                k for k in _KEYS
                if k in ind_arrays and k in dep_arrays
            ]

        fss = {
            key: _fss_from_arrays(ind_arrays[key], dep_arrays[key])
            for key in shared_keys_cache[pair]
        }
        output[ind_name].append({dep_name: fss})

    # --- write result ---
    stem = Path(forecast_name).stem
    (fss_dir / f"{stem}.json").write_text(json.dumps(output, indent=4))
    return forecast_name


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class DetermineFSS:

    VARS = _VARS
    L_VALUES = _L_VALUES

    def __init__(self, base_dir: str, max_workers: int | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.fraction_dir = self.base_dir / "_adapt" / "_fraction"
        self.fss_dir = self.base_dir / "_adapt" / "_fss"
        self.fss_dir.mkdir(parents=True, exist_ok=True)

        self._ens_dirs: list[Path] = sorted(
            (
                p for p in self.fraction_dir.iterdir()
                if p.is_dir() and p.name.endswith("_ens")
            ),
            key=_natural_sort_key,          # 1, 2, 3 ... 10, 11, not 1, 10, 11, 2
        )

        if not self._ens_dirs:
            raise RuntimeError(
                f"No ensemble directories found in {self.fraction_dir}"
            )

        # Default: one worker per CPU core, capped so we don't thrash I/O
        self._max_workers = max_workers or min(os.cpu_count() or 1, 8)

    # ------------------------------------------------------------------
    # Diagnostic — run this first to check variable names in your files
    # ------------------------------------------------------------------

    def diagnose(self, n_files: int = 3) -> None:
        """
        Opens the first n_files NetCDF files from the first ensemble dir
        and prints their variable names, so you can verify they match
        the expected keys (_KEYS).

        Usage:
            DetermineFSS(path).diagnose()
        """
        first_dir = self._ens_dirs[0]
        nc_files = sorted(first_dir.glob("*.nc"))[:n_files]

        if not nc_files:
            print(f"[DIAGNOSE] No .nc files found in {first_dir}")
            return

        print(f"\n[DIAGNOSE] Checking {len(nc_files)} file(s) in: {first_dir}")
        print(f"[DIAGNOSE] Expected keys: {_KEYS}\n")

        for nc_file in nc_files:
            with xr.open_dataset(nc_file) as ds:
                available = sorted(ds.variables)
                matched = [k for k in _KEYS if k in ds.variables]
                missing = [k for k in _KEYS if k not in ds.variables]

                print(f"  File     : {nc_file.name}")
                print(f"  All vars : {available}")
                print(f"  Matched  : {matched}")
                print(f"  Missing  : {missing}")
                print()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compile_fractions_time(self) -> None:
        """
        Creates one FSS JSON file per forecast time.
        Forecast times are processed in parallel across CPU cores.
        """
        sample_files = sorted(self._ens_dirs[0].glob("*.nc"))
        if not sample_files:
            raise RuntimeError(
                f"No NetCDF files found in {self._ens_dirs[0]}"
            )

        forecast_names = [f.name for f in sample_files]
        ens_dirs = self._ens_dirs
        fss_dir = self.fss_dir

        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            with tqdm(
                total=len(forecast_names),
                desc="Forecast Times",
                unit="file",
            ) as pbar:
                futures = {
                    pool.submit(
                        _process_forecast_file,
                        name,
                        ens_dirs,
                        fss_dir,
                    ): name
                    for name in forecast_names
                }

                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        tqdm.write(f"[ERROR] {name}: {exc}")
                    pbar.update(1)
                    pbar.set_postfix(last=name)


if __name__ == "__main__":
    path = (
        r"D:\rsderamos\Operational_06_18_2026\Operations"
        r"\meteo_database\ecmwf_meteo\20260621_00z"
    )

    fss = DetermineFSS(path)

    # Step 1: run this first to confirm variable names match
    #fss.diagnose()

    # Step 2: once confirmed, comment out diagnose() and run this
    fss.compile_fractions_time()