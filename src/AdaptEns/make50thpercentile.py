# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com

Optimized v7 (SSD deployment):
- n_outer bumped to min(8, cpu_count-1) — SSD handles concurrent reads well
- h5netcdf engine for faster writes (now that writes are the new bottleneck)
- Tasks sorted largest-first to avoid stragglers
- Outer mp.Pool: parallelizes across 51 timestep files
- Inner ThreadPoolExecutor: parallelizes median across variables per timestep
- Corrupt/truncated file detection before processing
- zlib compression on output
"""

import os
import multiprocessing as mp
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import xarray as xr
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Inner worker — runs in a thread (np.nanmedian releases the GIL)
# ---------------------------------------------------------------------------
def _median_one_var(args: tuple) -> tuple[str, np.ndarray, dict]:
    """Compute nanmedian across ensemble dim (axis 0) for one variable."""
    var_name, data, attrs = args
    result = np.nanmedian(data, axis=0)
    return var_name, result, attrs


# ---------------------------------------------------------------------------
# Outer worker — runs in a process
# ---------------------------------------------------------------------------
def _compute_p50(args: tuple) -> tuple[str, str | None]:
    """
    Load all ensemble members for one timestep, compute per-variable median
    using threads, and write output.

    Returns (filename, None) on success, (filename, error_msg) on failure.
    """
    filename, nc_files, out_dir, n_inner = args
    datasets = []

    for nc_file in nc_files:
        try:
            ds = xr.open_dataset(nc_file, engine="netcdf4")
            ds.load()  # catches corrupt/truncated files early
            datasets.append(ds)
        except Exception as e:
            warnings.warn(f"[SKIP corrupt file] {nc_file}: {e}")

    if not datasets:
        return filename, "No valid ensemble members found"

    try:
        ds_ens = xr.concat(datasets, dim="ensemble")

        var_tasks = [
            (var, ds_ens[var].values, ds_ens[var].attrs)
            for var in ds_ens.data_vars
        ]

        n_threads = min(n_inner, len(var_tasks))
        with ThreadPoolExecutor(max_workers=n_threads) as tex:
            results = list(tex.map(_median_one_var, var_tasks))

        ds_ref = datasets[0]
        coords = {k: v for k, v in ds_ref.coords.items() if k != "ensemble"}

        data_vars = {
            var_name: xr.Variable(
                [d for d in ds_ens[var_name].dims if d != "ensemble"],
                result,
                attrs,
            )
            for var_name, result, attrs in results
        }

        ds_p50 = xr.Dataset(data_vars, coords=coords, attrs=ds_ens.attrs)

        output_file = os.path.join(out_dir, filename)
        encoding = {
            var: {"zlib": True, "complevel": 4, "shuffle": True}
            for var in ds_p50.data_vars
        }
        # h5netcdf is faster than netcdf4 for writes — good fit for SSD
        ds_p50.to_netcdf(output_file, encoding=encoding, engine="h5netcdf")
        return filename, None

    except Exception as e:
        return filename, str(e)

    finally:
        for ds in datasets:
            ds.close()


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------
class make_50th_percentile:

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.adapt_dir = self.base_dir / "_adapt"

    # ------------------------------------------------------------------
    def _collect_tasks(self) -> dict[str, list[str]]:
        """Return {filename: [path_in_ens1, path_in_ens2, ...]} mapping."""
        timestep_files: dict[str, list[str]] = defaultdict(list)

        for ens_dir in self.base_dir.iterdir():
            if ens_dir.is_dir() and ens_dir.name.endswith("_ens"):
                for nc_file in ens_dir.glob("*.nc"):
                    timestep_files[nc_file.name].append(str(nc_file))

        return dict(timestep_files)

    # ------------------------------------------------------------------
    def make_50th_percentile(self, n_workers: int | None = None) -> None:
        out_dir = self.adapt_dir / "_50th_percentile"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestep_files = self._collect_tasks()

        if not timestep_files:
            print("No NetCDF files found.")
            return

        total_tasks = len(timestep_files)
        total_cores = mp.cpu_count()

        if n_workers is None:
            # SSD handles concurrent reads well — bump outer workers to 8
            n_outer = min(8, max(1, total_cores - 1))
        else:
            n_outer = n_workers

        n_inner = max(1, total_cores // n_outer)

        print(
            f"Processing {total_tasks} timesteps | "
            f"{n_outer} processes x {n_inner} threads "
            f"({n_outer * n_inner} cores active)"
        )

        # Sort largest files first to avoid a straggler slowing the final batch
        task_args = sorted(
            [
                (filename, nc_files, str(out_dir), n_inner)
                for filename, nc_files in timestep_files.items()
            ],
            key=lambda x: sum(os.path.getsize(f) for f in x[1]),
            reverse=True,
        )

        errors = []

        with mp.Pool(processes=n_outer) as pool:
            with tqdm(total=total_tasks, desc="Creating 50th percentile", unit="file") as pbar:
                for filename, error in pool.imap_unordered(_compute_p50, task_args):
                    if error:
                        errors.append((filename, error))
                        print(f"\n[ERROR] {filename}: {error}")
                    pbar.update(1)

        if errors:
            print(f"\n{len(errors)} file(s) failed:")
            for fname, err in errors:
                print(f"  {fname}: {err}")

        print(f"\nFinished. Outputs saved to:\n{out_dir}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"
    make_50th_percentile(path).make_50th_percentile()