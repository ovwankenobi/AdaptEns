# `compute_fraction.py`

`compute_fraction.py` computes neighborhood event fractions for each ensemble NetCDF file.

It compares each ensemble variable against the matching threshold field from `_adapt/_50th_percentile` (written by [`make_threshold.py`](make_threshold.md)). The result is written to `_adapt/_fraction/<member>_ens/` with the same timestep filename.

**Pipeline position:** stage 3 of 7. Run it after `make_threshold.py` and before [`make_fss_disp.py`](make_fss_disp.md).

## How to use the module

### Command line

```bash
python -m AdaptEns.compute_fraction "<base_dir>" "<compute_timestep>"
```

| Argument | Meaning |
| --- | --- |
| `<base_dir>` | Forecast-cycle folder that already contains `*_ens/` folders and `_adapt/_50th_percentile/`. |
| `<compute_timestep>` | `ALL` for every timestep, or an integer `N` for the first `N` timesteps. |

### As an imported class

```python
from AdaptEns.compute_fraction import MakeFraction

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

MakeFraction(path, compute_timestep="ALL").compute_fraction()
```

## `MakeFraction`

### Constructor

```python
MakeFraction(base_dir, compute_timestep="ALL")
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder containing ensemble output folders and `_adapt/_50th_percentile`. |
| `compute_timestep` | `"ALL"` processes every timestep; an integer `N` processes only the first `N` timesteps (via `_limit_timesteps`). |

### `compute_fraction()`

Builds a processing queue for every NetCDF file in every `*_ens` folder, then processes the queue with a multiprocessing pool. This method:

1. Sets the threshold directory to `<base_dir>/_adapt/_50th_percentile`.
2. Sets the output directory to `<base_dir>/_adapt/_fraction`.
3. Creates matching member output folders such as `_fraction/1_ens`.
4. Applies `compute_timestep` to limit how many timesteps each member contributes.
5. Skips files with a missing threshold (prints a `[WARN]`).
6. Uses up to `mp.cpu_count()` workers, capped by the number of queued files.
7. Prints warnings or errors after processing.

## Variables and neighborhoods

```python
VARS     = ["barometric_pressure", "wind_u", "wind_v"]
L_VALUES = [1, 3, 5]
```

For every variable and every `L`, one output variable is written. The filter size is `2 * L + 1`.

| Output variable example | Meaning |
| --- | --- |
| `barometric_pressure_L1` | Fraction of grid cells meeting the threshold in a `3 x 3` neighborhood. |
| `barometric_pressure_L3` | Fraction in a `7 x 7` neighborhood. |
| `barometric_pressure_L5` | Fraction in an `11 x 11` neighborhood. |
| `wind_u_L1`, `wind_v_L1` | Same calculation for the wind components. |

## Folder layout

Input:

```text
20260701_06z/
|-- 1_ens/
|-- 2_ens/
|-- ...
`-- _adapt/
    `-- _50th_percentile/
```

Output:

```text
20260701_06z/
`-- _adapt/
    `-- _fraction/
        |-- 1_ens/
        |   |-- ecmwf_meteo.20260701_0600.nc
        |   `-- ...
        |-- 2_ens/
        `-- ...
```

## Helper functions

| Function | Purpose |
| --- | --- |
| `_limit_timesteps(items, compute_timestep)` | Trims an ordered list of timestep files to `ALL` or the first `N`. |
| `_read_arrays(path)` | Reads only `barometric_pressure`, `wind_u`, `wind_v` as raw `float32` arrays via `netCDF4.Dataset` (faster than xarray for small files). |
| `_read_coords(path)` | Reads coordinate variables, dimensions, and global attributes from a reference file to copy into the output. |
| `_compute_fractions_fast(fcst, thres)` | Builds binary event fields where `forecast >= threshold`, stacks them, and applies `scipy.ndimage.uniform_filter` once per `L` (first axis is a batch dimension, so variables do not cross-contaminate). |
| `_write_output(out_file, fractions, coords)` | Writes the fraction arrays with `netCDF4.Dataset`. |
| `_process_file(args)` | File-level worker: read arrays, compute fractions, copy coords, write output. |

## NetCDF encoding

Fractions are stored as `int16` with:

| Encoding item | Value |
| --- | --- |
| `scale_factor` | `0.01` |
| `add_offset` | `0.0` |
| `_FillValue` | `-32768` |
| compression | disabled for faster writes |

Stored values represent fractions clipped to `[0, 1]`.

## Notes and assumptions

- Run this after `make_threshold.py` has created `_adapt/_50th_percentile`.
- Only `barometric_pressure`, `wind_u`, and `wind_v` are processed; `precipitation` is not.
- Output variable names are fixed as `<variable>_L<L>`.
- The `int16 + scale_factor 0.01` storage is what the next stage (`make_fss_disp.py`) multiplies back by `0.01` on read.
