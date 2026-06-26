# `fraction.py`

`fraction.py` computes neighborhood event fractions for each ensemble NetCDF file.

It compares each ensemble variable against the matching threshold field from `_adapt/_50th_percentile`. The result is written to `_adapt/_fraction/<member>_ens/` with the same timestep filename.

## Main Workflow

```text
Ensemble NetCDF file + matching 50th percentile threshold file
    -> read selected variables as NumPy arrays
    -> build binary event fields where forecast >= threshold
    -> apply neighborhood uniform filters for L1, L3, and L5
    -> write fraction NetCDF file
```

## Variables and Neighborhoods

The module processes these variables:

```python
VARS = ["barometric_pressure", "wind_u", "wind_v"]
L_VALUES = [1, 3, 5]
```

For every variable and every `L`, it writes one output variable:

| Output variable example | Meaning |
| --- | --- |
| `barometric_pressure_L1` | Fraction of grid cells meeting the threshold in a `3 x 3` neighborhood. |
| `barometric_pressure_L3` | Fraction in a `7 x 7` neighborhood. |
| `barometric_pressure_L5` | Fraction in an `11 x 11` neighborhood. |
| `wind_u_L1` | Same calculation for `wind_u`. |
| `wind_v_L1` | Same calculation for `wind_v`. |

The filter size is computed as `2 * L + 1`.

## Input Folder

The class receives `base_dir`, which should contain ensemble folders and the threshold folder:

```text
20260621_00z/
|-- 1_ens/
|-- 2_ens/
|-- ...
`-- _adapt/
    `-- _50th_percentile/
```

For each file in each `*_ens` folder, the module looks for a matching threshold file:

```text
<base_dir>/_adapt/_50th_percentile/<same_filename>.nc
```

Missing threshold files are reported with a warning and skipped.

## Output Folder

Fraction outputs are written to:

```text
<base_dir>/_adapt/_fraction/<member>_ens/
```

Example:

```text
20260621_00z/
`-- _adapt/
    `-- _fraction/
        |-- 1_ens/
        |   |-- ecmwf_meteo.20260621_0000.nc
        |   |-- ecmwf_meteo.20260621_0300.nc
        |   `-- ...
        |-- 2_ens/
        `-- ...
```

## Helper Functions

### `_read_arrays(path)`

Reads only `barometric_pressure`, `wind_u`, and `wind_v` from a NetCDF file. It uses `netCDF4.Dataset` directly instead of `xarray` for faster small-file reads.

### `_read_coords(path)`

Reads coordinate variables, dimensions, and global attributes from a reference ensemble file. These are copied into the fraction output.

### `_compute_fractions_fast(fcst, thres)`

Creates binary event fields where:

```python
forecast >= threshold
```

It stacks the event arrays and applies `scipy.ndimage.uniform_filter` for each `L` value. The first axis is treated as a batch dimension, so each variable is filtered independently.

### `_write_output(out_file, fractions, coords)`

Writes the fraction arrays to NetCDF using `netCDF4.Dataset`.

Fractions are stored as `int16` with:

| Encoding item | Value |
| --- | --- |
| `scale_factor` | `0.01` |
| `add_offset` | `0.0` |
| `_FillValue` | `-32768` |
| compression | disabled for faster writes |

The stored values represent fractions clipped to `[0, 1]`.

### `_process_file(args)`

Processes one ensemble file, one threshold file, and one output file. It reads arrays, computes the fractions, copies coordinates, and writes the output.

## `MakeFraction`

Primary class for generating all fraction files.

### Constructor

```python
MakeFraction(base_dir)
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder containing ensemble output folders and `_adapt/_50th_percentile`. |

### `fraction()`

Builds a processing queue for every NetCDF file in every `*_ens` folder, then processes the queue with a multiprocessing pool.

This method:

1. Sets the threshold directory to `<base_dir>/_adapt/_50th_percentile`.
2. Sets the output directory to `<base_dir>/_adapt/_fraction`.
3. Creates matching member output folders such as `_fraction/1_ens`.
4. Skips files with missing thresholds.
5. Uses up to `mp.cpu_count()` workers, capped by the number of queued files.
6. Prints warnings or errors after processing.

## Example

```python
from AdaptEns.fraction import MakeFraction

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"

MakeFraction(path).fraction()
```

## Notes and Assumptions

- Run this after `make_threshold.py` has created `_adapt/_50th_percentile`.
- Only `barometric_pressure`, `wind_u`, and `wind_v` are processed.
- `precipitation` is not included in the current fraction calculation.
- Output variable names are fixed as `<variable>_L<L>`.
- The script block under `if __name__ == "__main__":` is an example run path for a local Windows-style operational folder.
