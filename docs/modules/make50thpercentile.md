# `make50thpercentile.py`

`make50thpercentile.py` creates a 50th percentile, or median, NetCDF product from ensemble-member NetCDF files.

It is designed to run after `grib_decoder.py`. The decoder writes folders such as `1_ens`, `2_ens`, and so on. This module reads matching timestep files across those folders and writes one median NetCDF file per timestep.

## Main Workflow

```text
Per-member NetCDF files
    -> group files by matching timestep filename
    -> load all available ensemble members for one timestep
    -> compute nanmedian across the ensemble dimension
    -> write one NetCDF file to _adapt/_50th_percentile
```

## Input Folder

The class receives `base_dir`, which should be the forecast-cycle folder containing the ensemble folders:

```text
20260621_00z/
|-- 1_ens/
|   |-- ecmwf_meteo.20260621_0000.nc
|   |-- ecmwf_meteo.20260621_0300.nc
|   `-- ...
|-- 2_ens/
|   |-- ecmwf_meteo.20260621_0000.nc
|   |-- ecmwf_meteo.20260621_0300.nc
|   `-- ...
`-- ...
```

Any directory inside `base_dir` whose name ends with `_ens` is treated as an ensemble-member folder.

## Output Folder

Outputs are written to:

```text
<base_dir>/_adapt/_50th_percentile/
```

Example:

```text
20260621_00z/
`-- _adapt/
    `-- _50th_percentile/
        |-- ecmwf_meteo.20260621_0000.nc
        |-- ecmwf_meteo.20260621_0300.nc
        `-- ...
```

The output filename is the same as the timestep filename being processed.

## `_median_one_var(args)`

Computes the median for one variable.

Expected `args` tuple:

| Position | Name | Meaning |
| --- | --- | --- |
| `0` | `var_name` | Variable name from the NetCDF dataset. |
| `1` | `data` | NumPy array with ensemble as axis `0`. |
| `2` | `attrs` | Original variable attributes to copy to the output. |

The function uses `np.nanmedian(data, axis=0)`, so missing values are ignored when calculating the median.

## `_compute_p50(args)`

Internal worker that processes one timestep filename.

Expected `args` tuple:

| Position | Name | Meaning |
| --- | --- | --- |
| `0` | `filename` | NetCDF filename shared by ensemble members. |
| `1` | `nc_files` | List of matching NetCDF files from ensemble folders. |
| `2` | `out_dir` | Destination folder for 50th percentile outputs. |
| `3` | `n_inner` | Number of threads for per-variable median calculation. |

This worker:

1. Opens each NetCDF file with `xarray.open_dataset(..., engine="netcdf4")`.
2. Calls `load()` to catch corrupt or truncated files early.
3. Skips unreadable files with a warning.
4. Concatenates valid datasets along a new `ensemble` dimension.
5. Computes the median for each data variable using a thread pool.
6. Rebuilds an `xarray.Dataset` without the `ensemble` dimension.
7. Writes the output using the `h5netcdf` engine.

If all ensemble files for a timestep are invalid, it returns an error for that filename instead of writing an output file.

## `make_50th_percentile`

Primary class for creating the median product.

### Constructor

```python
make_50th_percentile(base_dir)
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder containing ensemble output folders such as `1_ens`, `2_ens`, and so on. |

The constructor also sets:

| Attribute | Value |
| --- | --- |
| `base_dir` | The input forecast-cycle folder as a `Path`. |
| `adapt_dir` | `<base_dir>/_adapt`. |

### `_collect_tasks()`

Builds a dictionary of timestep work items:

```python
{
    "ecmwf_meteo.20260621_0000.nc": [
        ".../1_ens/ecmwf_meteo.20260621_0000.nc",
        ".../2_ens/ecmwf_meteo.20260621_0000.nc",
        ...
    ],
}
```

This lets the main method process one forecast timestep at a time across all available ensemble members.

### `make_50th_percentile(n_workers=None)`

Creates the 50th percentile NetCDF files.

This method:

1. Creates `<base_dir>/_adapt/_50th_percentile`.
2. Collects all timestep tasks from `_ens` folders.
3. Selects worker counts:
   - `min(8, cpu_count - 1)` outer processes by default.
   - `cpu_count // n_outer` inner threads per process.
4. Sorts tasks largest-first to reduce slow final batches.
5. Uses a multiprocessing pool to process timestep files.
6. Prints any failed filenames and their errors.
7. Prints the final output folder.

## NetCDF Encoding

Each output variable is written with:

| Encoding option | Value |
| --- | --- |
| `zlib` | `True` |
| `complevel` | `4` |
| `shuffle` | `True` |

The files are written with the `h5netcdf` engine.

## Example

```python
from AdaptEns.make50thpercentile import make_50th_percentile

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"

make_50th_percentile(path).make_50th_percentile()
```

## Notes and Assumptions

- Run this after `grib_decoder.py` has created the ensemble NetCDF folders.
- The median is calculated independently for each variable and grid cell.
- Corrupt or truncated NetCDF files are skipped with a warning.
- If a timestep has no valid ensemble files, no 50th percentile file is written for that timestep.
- The script block under `if __name__ == "__main__":` is an example run path for a local Windows-style operational folder.
