from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import multiprocessing as mp

import numpy as np
import xarray as xr
from scipy.ndimage import uniform_filter
from tqdm import tqdm

L_VALUES   = [1, 3, 5]
VARS       = ["barometric_pressure", "wind_u", "wind_v"]
CHUNK_SIZE = {"time": 10}

# ── output encoding ────────────────────────────────────────────────────────────
def _nc_encoding(var_names: list[str]) -> dict:
    return {
        v: {
            "dtype":        "int16",
            "scale_factor": np.float32(0.01),
            "add_offset":   np.float32(0.0),
            "_FillValue":   np.int16(-32768),
        }
        for v in var_names
    }


# ── per-(var, L) worker — called from a thread ────────────────────────────────
def _filter_one(
    key: str,
    event: np.ndarray,          # read-only view, already float32
    dims: tuple,
    coords: dict,
    L: int,
) -> tuple[str, xr.DataArray]:
    """
    Runs uniform_filter for one (var, L) pair.
    scipy releases the GIL during the C call, so threads run truly in parallel.
    Returns (key, DataArray) — no shared mutable state.
    """
    size = 2 * L + 1
    if event.ndim == 2:
        frac = uniform_filter(event, size=size, mode="constant", cval=0.0)
    else:
        frac = uniform_filter(event, size=(1, size, size), mode="constant", cval=0.0)

    return key, xr.DataArray(frac.astype(np.float32), dims=dims, coords=coords)


# ── core compute — fan-out across (var, L) pairs via thread pool ──────────────
def _compute_fractions(
    fcst_ds:  xr.Dataset,
    thres_ds: xr.Dataset,
    max_threads: int | None = None,
) -> dict[str, xr.DataArray]:
    """
    1. Compute binary event arrays once per variable (cheap, sequential).
    2. Fan out all (var, L) uniform_filter calls to a ThreadPoolExecutor.
       scipy's uniform_filter releases the GIL → true parallelism with threads.
    3. Collect results in insertion order.

    max_threads defaults to len(VARS) * len(L_VALUES) = 9, i.e. one thread
    per task.  Tune down if memory is tight (each thread holds one float32
    copy of the (T,H,W) array).
    """
    # ── step 1: event arrays, one per var (sequential, very cheap) ────────────
    tasks: list[tuple[str, np.ndarray, tuple, dict, int]] = []

    for var in VARS:
        if var not in fcst_ds or var not in thres_ds:
            continue
        da_fcst  = fcst_ds[var]
        da_thres = thres_ds[var]
        # Compute once; passed as a read-only view to every L thread for this var
        event = (da_fcst.values >= da_thres.values).astype(np.float32)
        dims   = da_fcst.dims
        coords = dict(da_fcst.coords)   # plain dict — safe to share across threads

        for L in L_VALUES:
            tasks.append((f"{var}_L{L}", event, dims, coords, L))

    if not tasks:
        return {}

    # ── step 2: parallel uniform_filter calls ─────────────────────────────────
    n_threads = max_threads or len(tasks)   # default: one thread per task
    fraction_vars: dict[str, xr.DataArray] = {}

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = {
            pool.submit(_filter_one, key, event, dims, coords, L): key
            for key, event, dims, coords, L in tasks
        }
        for future in as_completed(futures):
            key, da = future.result()   # re-raises any exception from the thread
            fraction_vars[key] = da

    # Restore deterministic output order (as_completed is non-deterministic)
    ordered_keys = [t[0] for t in tasks]
    return {k: fraction_vars[k] for k in ordered_keys if k in fraction_vars}


# ── file-level worker — unchanged API, multiprocessing-safe ──────────────────
def _process_file(args: tuple[Path, Path, Path]) -> str | None:
    ens_file, threshold_file, out_file = args
    fcst_ds = thres_ds = None
    try:
        fcst_ds  = xr.open_dataset(ens_file,       chunks=CHUNK_SIZE)
        thres_ds = xr.open_dataset(threshold_file, chunks=CHUNK_SIZE)
        fcst_ds.load()
        thres_ds.load()

        fraction_vars = _compute_fractions(fcst_ds, thres_ds)

        if not fraction_vars:
            return f"[WARN] No output produced for {ens_file.name}"

        out_ds = xr.Dataset(fraction_vars)
        out_ds.to_netcdf(out_file, encoding=_nc_encoding(list(fraction_vars)))
        return None

    except Exception as exc:
        return f"[ERROR] {ens_file.name}: {exc}"

    finally:
        for ds in (fcst_ds, thres_ds):
            if ds is not None:
                try:
                    ds.close()
                except Exception:
                    pass


# ── orchestrator — unchanged ──────────────────────────────────────────────────
class MakeFraction:
    def __init__(self, base_dir: str) -> None:
        self.base_dir  = Path(base_dir)
        self.adapt_dir = self.base_dir / "_adapt"

    def fraction(self) -> None:
        threshold_dir = self.adapt_dir / "_50th_percentile"
        fraction_dir  = self.adapt_dir / "_fraction"

        queue: list[tuple[Path, Path, Path]] = []
        for ens_dir in sorted(self.base_dir.glob("*_ens")):
            if not ens_dir.is_dir():
                continue
            out_dir = fraction_dir / ens_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            for ens_file in sorted(ens_dir.glob("*.nc")):
                threshold_file = threshold_dir / ens_file.name
                if not threshold_file.exists():
                    print(f"[WARN] Missing threshold file: {threshold_file}")
                    continue
                queue.append((ens_file, threshold_file, out_dir / ens_file.name))

        if not queue:
            print("No files found.")
            return

        n_workers = max(1, mp.cpu_count() - 1)
        errors: list[str] = []

        with mp.Pool(n_workers) as pool:
            for result in tqdm(
                pool.imap_unordered(_process_file, queue),
                total=len(queue),
                desc="Creating fractions",
            ):
                if result is not None:
                    errors.append(result)

        if errors:
            print(f"\n{len(errors)} file(s) had issues:")
            for e in errors:
                print(" ", e)
        else:
            print("All files processed successfully.")


if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"
    MakeFraction(path).fraction()