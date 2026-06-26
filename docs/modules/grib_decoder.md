# `grib_decoder.py`

`grib_decoder.py` converts ECMWF GRIB forecast data into NetCDF files organized by ensemble member and forecast time.

The module uses:

- `eccodes` to read and write raw GRIB messages.
- `xarray` with the `cfgrib` engine to load split GRIB files as datasets.
- `multiprocessing.Pool` to split the original GRIB files in parallel.
- `concurrent.futures.ProcessPoolExecutor` to convert ensemble-member folders into NetCDF outputs in parallel.

## Main Workflow

```text
Raw GRIB files
    -> grib_parameters()
Temporary GRIB files grouped by member, variable, and step
    -> loadgrib()
Per-member, per-time NetCDF files
```

For a Day 0 to Day 5 forecast range, the typical runtime is about `30 seconds` for `grib_parameters()` and about `1 minute` for writing the NetCDF files in `loadgrib()`.

## Constants

```python
VARS = {"tp", "10u", "10v", "msl"}
```

Only messages with these GRIB `shortName` values are kept. All other GRIB messages are skipped.

## `process_file(args)`

Splits one raw GRIB file into smaller temporary GRIB files.

Expected `args` tuple:

| Position | Name | Meaning |
| --- | --- | --- |
| `0` | `filepath` | Raw GRIB file to read. |
| `1` | `tmp_param` | Temporary output folder, usually `<base_dir>/_tmp_param`. |
| `2` | `is_ensemble` | Whether to process ensemble members `1..50` or deterministic member `50`. |

For each GRIB message, the function:

1. Reads the next message using `codes_grib_new_from_file`.
2. Gets the GRIB `shortName`; messages outside `VARS` are ignored.
3. Gets `perturbationNumber`.
4. Keeps members `1..50` when `is_ensemble=True`; otherwise keeps only member `50`.
5. Gets the forecast `step`.
6. Writes the message to:

```text
<tmp_param>/<perturbationNumber>_ens/<shortName>_step<step>.grib
```

Open file handles are cached in `local_outputs` while the source file is processed, then closed in the `finally` block.

## `_process_member(args)`

Internal worker used by `loadgrib()`. It is underscore-prefixed because it is not part of the public workflow, but it is documented here because it lives inside the public `grib_decoder.py` module and explains how output files are produced.

Expected `args` tuple:

| Position | Name | Meaning |
| --- | --- | --- |
| `0` | `member` | Ensemble member number. |
| `1` | `tmp_param` | Temporary folder containing split GRIB files. |
| `2` | `variables` | Variables to load: `10u`, `10v`, `msl`, `tp`. |
| `3` | `name` | Output filename prefix, currently `ecmwf_meteo`. |
| `4` | `base_dir` | Parent folder where final ensemble folders are written. |

For each variable, the worker:

1. Finds matching files with `<var>_step*.grib`.
2. Opens each file with `xr.open_dataset(..., engine="cfgrib")`.
3. Reads the forecast `step` coordinate.
4. Converts `step` to integer forecast hours.
5. Sorts datasets by forecast step.
6. Concatenates all steps for that variable.

After all variables are loaded, it merges the datasets, converts total precipitation into precipitation rate, renames variables, computes real datetimes, and writes NetCDF files.

## `decode_Grib`

Primary class for running the decoder.

### Constructor

```python
decode_Grib(
    path_gribfolder=None,
    is_ensemble=True,
    delete_tmp_folders=False,
)
```

| Parameter | Description |
| --- | --- |
| `path_gribfolder` | Folder containing raw GRIB files. |
| `is_ensemble` | If `True`, process members `1..50`. If `False`, process member `50`. |
| `delete_tmp_folders` | If `True`, remove temporary folders after processing stages. |

The constructor also sets:

| Attribute | Value |
| --- | --- |
| `name` | `ecmwf_meteo`, used as the NetCDF filename prefix. |
| `base_dir` | Parent folder of `path_gribfolder`. |

### `grib_parameters()`

Creates the temporary split-GRIB folder and fills it.

This method:

1. Creates `<base_dir>/_tmp_param`.
2. Lists all files in `path_gribfolder`.
3. Uses a multiprocessing pool to run `process_file()` on every raw GRIB file.
4. Displays progress with `tqdm`.
5. Prints elapsed time.
6. Optionally deletes `path_gribfolder` when `delete_tmp_folders=True`.

Run this method before `loadgrib()`.

### `loadgrib()`

Builds final NetCDF files from `_tmp_param`.

This method:

1. Sets the variables to `("10u", "10v", "msl", "tp")`.
2. Selects ensemble members:
   - `range(1, 51)` when `is_ensemble=True`.
   - `[50]` when `is_ensemble=False`.
3. Opens one sample `msl` GRIB file to count forecast steps.
4. Uses a process pool to run `_process_member()` for each member.
5. Updates a progress bar as NetCDF files are written.
6. Optionally deletes `_tmp_param` when `delete_tmp_folders=True`.

## NetCDF Time Handling

The GRIB files carry an initialization time and forecast step. The module computes output times like this:

```python
init_time = pd.Timestamp(ds.coords["time"].values)
times = init_time + pd.to_timedelta(ds.step.values, unit="h")
```

Then it swaps the dimension from `step` to `time`, so each written NetCDF file represents one real forecast datetime.

## NetCDF Encoding

All data variables are written with:

| Encoding option | Value |
| --- | --- |
| `zlib` | `True` |
| `complevel` | `1` |
| `dtype` | `float32` |

The files are written with the `h5netcdf` engine.

## Example

```python
from AdaptEns.grib_decoder import decode_Grib

decoder = decode_Grib(
    path_gribfolder=r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib",
    is_ensemble=True,
    delete_tmp_folders=False,
)

decoder.grib_parameters()
decoder.loadgrib()
```

## Notes and Assumptions

- `loadgrib()` expects `_tmp_param` to already exist, so `grib_parameters()` should run first.
- The code assumes `msl_step*.grib` exists in the first selected ensemble folder.
- The output filename prefix is fixed as `ecmwf_meteo`.
- The script block under `if __name__ == "__main__":` is an example run path for a local Windows-style operational folder.
