# `grib_decoder.py`

`grib_decoder.py` converts ECMWF GRIB forecast data into NetCDF files, in either the CoSMoS layout (one file per member per timestep) or the SCHISM layout (one file per member).

**Pipeline position:** stage 1 of 7. It always runs, whether or not the ranking stages run afterwards.

The module uses:

- `eccodes` to read and write raw GRIB messages.
- `xarray` with the `cfgrib` engine to load the split GRIB files as datasets.
- `multiprocessing.Pool` to split the raw GRIB files in parallel, and again to build each member's NetCDF output in parallel.

## Main workflow

```text
<path>/_tmp_grib/          raw GRIB files
    -> grib_parameters()
<path>/_tmp_param/<member>_ens/<var>_step<step>.grib
    -> loadgrib()
<path>/<member>_ens/<name>.YYYYMMDD_HHMM.nc         (type="cosmos", or schism + adapt_ens)
<path>/<name>_<YYYYMMDDHHMM>_<member>.nc            (type="schism")
```

For a Day 0 to Day 5 forecast range, `grib_parameters()` typically takes about `30 seconds` and `loadgrib()` about `1 minute` in the CoSMoS layout.

## Ensemble members

| Member | Source files | Meaning |
| --- | --- | --- |
| `0` | `E1D*` | HRES reference forecast (GRIB `perturbationNumber` 0). |
| `1`–`50` | `E1E*` | ENS perturbed members. |

`is_ensemble=True` keeps members `0..50`; `is_ensemble=False` keeps member `0` only. Both file streams are downloaded by `sKit_meteo.ecmwf.download_data` in SurgeKit.

## Constants

| Name | Value | Purpose |
| --- | --- | --- |
| `VARS` | `{"tp", "10u", "10v", "msl"}` | GRIB `shortName` values to keep. All other messages are skipped. |
| `CFGRIB_NAMES` | `{"tp": "tp", "10u": "u10", "10v": "v10", "msl": "msl"}` | Variable name `cfgrib` gives each `shortName`, used to check that a file loaded correctly. |
| `OPEN_RETRIES` | `3` | How many times `_open_grib()` re-opens a file before giving up. |
| `SCHISM_ATTRS` | dict | CF attributes written on each variable and coordinate in the SCHISM file. |

## `decode_Grib`

Primary class for running the decoder.

### Constructor

```python
decode_Grib(
    path=None,
    is_ensemble=True,
    delete_tmp_folders=False,
    name=None,
    type="cosmos",
    adapt_ens=False,
    member_workers=None,
)
```

| Parameter | Description |
| --- | --- |
| `path` | Forecast cycle folder. The raw GRIB files are read from `<path>/_tmp_grib`, and all outputs are written to `path`. |
| `is_ensemble` | `True` processes members `0..50`; `False` processes member `0` only. |
| `delete_tmp_folders` | `True` removes `_tmp_grib` after `grib_parameters()` and `_tmp_param` after `loadgrib()`. |
| `name` | Output filename prefix. Pass it explicitly: the class default is `None`, which would produce filenames starting with `None`. The command-line entry point defaults to `ecmwf_meteo`. |
| `type` | `"cosmos"` or `"schism"` (case-insensitive). Selects the output layout. |
| `adapt_ens` | When `True` with `type="schism"`, also writes the CoSMoS layout so the ranking stages have input. Has no effect with `type="cosmos"`, which always writes that layout. |
| `member_workers` | Number of parallel member workers in `loadgrib()`. Defaults to `min(cpu_count - 1, 6)`, with a minimum of 1. |

### `grib_parameters()`

Splits the raw GRIB files into small per-member, per-variable, per-step files.

1. Creates `<path>/_tmp_param`.
2. Lists every file in `<path>/_tmp_grib`.
3. Runs `process_file()` on each file in a `multiprocessing.Pool` of `max(4, cpu_count - 1)` workers, with a `tqdm` progress bar.
4. Prints the elapsed time.
5. Deletes `_tmp_grib` when `delete_tmp_folders=True`.

Run this before `loadgrib()`; it sets `self.tmp_param`, which `loadgrib()` reads.

### `loadgrib()`

Builds the final NetCDF files from `_tmp_param`.

1. Selects the members (`0..50` or `[0]`).
2. Sizes the progress bar from the first member folder that exists, counting its `msl_step*.grib` files. Each member counts as that many files in the CoSMoS layout, plus one file in the SCHISM layout.
3. Runs `_process_member()` for each member in a `multiprocessing.Pool` of `member_workers` workers. The pool is capped because each worker holds a whole member in memory.
4. Deletes `_tmp_param` when `delete_tmp_folders=True`.

## `process_file(args)`

Splits one raw GRIB file. `args` is `(filepath, tmp_param, is_ensemble)`.

For each GRIB message, the function:

1. Skips it if its `shortName` is not in `VARS`.
2. Reads `perturbationNumber`, and keeps `0..50` when `is_ensemble=True`, or only `0` otherwise.
3. Reads the forecast `step`.
4. Appends the message to `<tmp_param>/<perturbationNumber>_ens/<shortName>_step<step>.grib`.

Open file handles are cached while the source file is processed, then closed in a `finally` block.

## `_process_member(args)`

Internal worker used by `loadgrib()`. `args` is `(member, tmp_param, variables, name, base_dir, type, adapt_ens)`. It returns `(member, files_written)`.

1. For each variable, loads every `<var>_step*.grib` file with `_open_grib()`, converts `step` to integer hours, sorts by step, and concatenates along `step`. Files that fail to load are reported and skipped.
2. Merges the variables into one dataset.
3. Converts cumulative `tp` into a precipitation rate (see [Precipitation](#precipitation)).
4. Converts `step` into real datetimes (`init_time + step`) and makes `time` the dimension.
5. Calls `_write_schism()` when `type == "schism"`.
6. Calls `_write_cosmos()` when `type == "cosmos"` or `adapt_ens` is `True`.

If the member folder is missing or holds no data, it prints a message and returns `(member, 0)`.

## `_open_grib(file, var)`

Opens one split GRIB file with `cfgrib` and checks that the expected variable (from `CFGRIB_NAMES`) is present. ecCodes can fail to parse its definitions when several workers start at once, which returns a dataset without the variable; in that case the function closes the dataset, waits `0.5 × attempt` seconds, and retries, up to `OPEN_RETRIES` times. It then raises `ValueError`.

## Output layouts

### CoSMoS (`_write_cosmos`)

One NetCDF file per timestep, in one folder per member:

```text
<path>/<member>_ens/<name>.YYYYMMDD_HHMM.nc
```

| Source name | Output name |
| --- | --- |
| `latitude` | `lat` (sorted ascending) |
| `longitude` | `lon` |
| `u10` | `wind_u` |
| `v10` | `wind_v` |
| `msl` | `barometric_pressure` |
| `tp` | `precipitation` |

The `time` coordinate is dropped from each single-timestep file; the time is carried by the filename.

### SCHISM (`_write_schism`)

One NetCDF file per member, holding every timestep:

```text
<path>/<name>_<YYYYMMDDHHMM>_<member>.nc      e.g. ECMWF_surf_202607010600_0.nc
```

| Property | Value |
| --- | --- |
| Dimensions | `(time, lat, lon)` |
| Latitude order | descending |
| Longitude order | ascending |
| Variables | `10u`, `10v`, `msl`, `precipitation` |
| Other coordinates | dropped (only `time`, `lat`, `lon` are kept) |
| `time` encoding | `hours since <init time>`, `proleptic_gregorian`, `float64` |
| Global attributes | `Conventions = CF-1.6`, `institution = European Centre for Medium-Range Weather Forecasts` |

Variable and coordinate attributes come from `SCHISM_ATTRS` (for example `msl` gets `standard_name = air_pressure_at_mean_sea_level` and `units = Pa`; `precipitation` gets `units = mm h**-1`).

### Encoding (both layouts)

All data variables are written with the `h5netcdf` engine and:

| Encoding option | Value |
| --- | --- |
| `zlib` | `True` |
| `complevel` | `1` |
| `dtype` | `float32` |

## Precipitation

GRIB `tp` is cumulative total precipitation in metres. The decoder differences consecutive steps, divides by the step length in hours, and multiplies by `1000`, giving a rate in mm/h. The first step is set to `0`, and any `NaN` is filled with `0`.

## Command line

```bash
python -m AdaptEns.grib_decoder "<path>" [is_ensemble] [delete_tmp_folders] [name] [type] [adapt_ens]
```

| Position | Argument | Default |
| --- | --- | --- |
| 1 | `path` | required |
| 2 | `is_ensemble` | `True` |
| 3 | `delete_tmp_folders` | `True` |
| 4 | `name` | `ecmwf_meteo` |
| 5 | `type` | `cosmos` |
| 6 | `adapt_ens` | `False` |

Booleans accept `1`, `true`, `yes`, `y`, `t` (case-insensitive) as `True`; anything else is `False`.

## Example

```python
from AdaptEns.grib_decoder import decode_Grib

decoder = decode_Grib(
    r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z",
    is_ensemble=True,
    delete_tmp_folders=False,
    name="ECMWF_surf",
    type="schism",
)

decoder.grib_parameters()
decoder.loadgrib()
```

## Notes and assumptions

- `loadgrib()` needs `grib_parameters()` to have run first in the same object.
- A member whose `_tmp_param/<member>_ens` folder is missing (for example when the `E1D` files were not downloaded) is skipped with a message, not treated as an error.
