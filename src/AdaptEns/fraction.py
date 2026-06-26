# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com
"""

from __future__ import annotations

from pathlib import Path
import multiprocessing as mp

import numpy as np
import netCDF4 as nc                    # direct NetCDF4 — much faster than xarray for small files
from scipy.ndimage import uniform_filter
from tqdm import tqdm

L_VALUES   = [1, 3, 5]
VARS       = ["barometric_pressure", "wind_u", "wind_v"]
OUT_KEYS   = [f"{v}_L{L}" for v in VARS for L in L_VALUES]   # 9 output names, fixed order

SCALE      = np.float32(0.01)
FILL_INT16 = np.int16(-32768)

# Pre-compute filter sizes once at import time
_SIZES = {L: 2 * L + 1 for L in L_VALUES}


# ── fast raw NetCDF4 read ──────────────────────────────────────────────────────
def _read_arrays(path: Path) -> dict[str, np.ndarray]:
    """
    Read only the variables we need as raw float32 numpy arrays.
    Skips xarray entirely — no coordinate parsing, no index building.
    """
    out = {}
    with nc.Dataset(path, "r") as ds:
        for var in VARS:
            if var in ds.variables:
                out[var] = ds.variables[var][:].astype(np.float32, copy=False)
    return out


def _read_coords(path: Path) -> dict:
    """
    Read coordinate metadata from one reference file for output writing.
    Only called once per file (from fcst path).
    """
    coords = {}
    with nc.Dataset(path, "r") as ds:
        for name in ds.dimensions:
            if name in ds.variables:
                coords[name] = {
                    "data":  ds.variables[name][:],
                    "units": getattr(ds.variables[name], "units", None),
                    "dtype": ds.variables[name].dtype,
                }
        coords["_dimensions"] = {
            name: len(dim)
            for name, dim in ds.dimensions.items()
        }    # name → size
        coords["_global_attrs"] = {
            k: getattr(ds, k) for k in ds.ncattrs()
        }
    return coords


# ── core compute — all 9 fractions in one numpy pass ─────────────────────────
def _compute_fractions_fast(
    fcst:  dict[str, np.ndarray],
    thres: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """
    Stack all (var, L) uniform_filter calls into a single (9, H, W) array,
    then filter the whole block at once.

    For 2D (H, W) arrays with no time dimension, uniform_filter on a
    (9, H, W) stack with size=(1, s, s) treats the first axis as a batch
    dimension — zero cross-contamination, one C call.
    """
    # 1. Build binary event arrays: shape (3, H, W)
    events = []
    present_vars = []
    for var in VARS:
        if var in fcst and var in thres:
            events.append((fcst[var] >= thres[var]).astype(np.float32))
            present_vars.append(var)

    if not events:
        return {}

    # 2. For each L, stack all var events and filter once
    results: dict[str, np.ndarray] = {}
    event_stack = np.stack(events, axis=0)      # (n_vars, H, W)

    for L in L_VALUES:
        size = _SIZES[L]
        # Filter all vars at once: (n_vars, H, W) with size=(1, s, s)
        frac_block = uniform_filter(
            event_stack, size=(1, size, size), mode="constant", cval=0.0
        )                                        # (n_vars, H, W)
        for i, var in enumerate(present_vars):
            results[f"{var}_L{L}"] = frac_block[i]

    return results


# ── fast raw NetCDF4 write ────────────────────────────────────────────────────
def _write_output(
    out_file: Path,
    fractions: dict[str, np.ndarray],
    coords: dict,
) -> None:
    """
    Write directly with netCDF4 — pre-allocate all variables, write in one pass.
    int16 + scale_factor gives the same precision as before at ~4× write speed.
    """
    with nc.Dataset(out_file, "w", format="NETCDF4") as ds:
        # Copy global attributes
        ds.setncatts(coords.get("_global_attrs", {}))

        # Create dimensions
        for dim_name, dim_size in coords["_dimensions"].items():
            ds.createDimension(dim_name, dim_size if dim_size > 0 else None)

        # Copy coordinate variables
        for name, meta in coords.items():
            if name.startswith("_"):
                continue
            if name not in ds.dimensions:
                continue
            v = ds.createVariable(name, meta["dtype"], (name,))
            v[:] = meta["data"]
            if meta["units"]:
                v.units = meta["units"]

        # Determine spatial dims (last two dims of any fraction array)
        sample = next(iter(fractions.values()))
        # find dimension names matching the spatial shape
        spatial_dims = [
            dim for dim, size in coords["_dimensions"].items()
            if size in sample.shape
        ][:2]    # take first two matching — lat, lon

        # Write fraction variables as int16 with scale_factor
        for key, arr in fractions.items():
            v = ds.createVariable(
                key, "i2", spatial_dims,
                fill_value=FILL_INT16,
                zlib=False,             # no compression — as fast as raw write
            )
            v.scale_factor = SCALE
            v.add_offset   = np.float32(0.0)
            # Quantise: clip to [0,1], scale to int16
            quantised = np.clip(np.round(arr / SCALE), -32767, 32767).astype(np.int16)
            v[:] = quantised


# ── file-level worker ─────────────────────────────────────────────────────────
def _process_file(args: tuple[Path, Path, Path]) -> str | None:
    ens_file, threshold_file, out_file = args
    try:
        fcst  = _read_arrays(ens_file)
        thres = _read_arrays(threshold_file)

        fractions = _compute_fractions_fast(fcst, thres)
        if not fractions:
            return f"[WARN] No output produced for {ens_file.name}"

        coords = _read_coords(ens_file)
        _write_output(out_file, fractions, coords)
        return None

    except Exception as exc:
        return f"[ERROR] {ens_file.name}: {exc}"


# ── orchestrator ──────────────────────────────────────────────────────────────
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

        # With 16+ cores and 500+ tiny files, maximise process count
        # Each worker is mostly waiting on disk, so go above cpu_count-1
        n_workers = min(mp.cpu_count(), len(queue))
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