# Input and Output Folder Structure

Every stage works inside one forecast-cycle folder (`path` / `base_dir`). `grib_decoder.py` reads the raw ECMWF GRIB files from its `_tmp_grib` subfolder and writes temporary files and NetCDF outputs into the cycle folder. `make_threshold.py` reads the ensemble NetCDF folders and writes median threshold products under `_adapt`. `compute_fraction.py` then compares each ensemble file against those thresholds and writes neighborhood fraction products.

## Input Folder

The cycle folder is passed to `decode_Grib(path=...)` (or `run_adapt_ens(path=...)`). The raw GRIB files must be in `<path>/_tmp_grib`, which is where SurgeKit's `bz2togrib` step puts them.

Example:

```text
Operations/
`-- meteo_database/
    `-- ecmwf_meteo/
        `-- 20260621_00z/
            `-- _tmp_grib/
                |-- input_file_001.grib
                |-- input_file_002.grib
                `-- ...
```

In this example:

| Item | Value |
| --- | --- |
| `path` / `base_dir` | `...\20260621_00z` |
| GRIB input folder | `...\20260621_00z\_tmp_grib` |

The module reads every file directly inside `_tmp_grib`. The filenames are not interpreted by the code; each file is opened as a GRIB stream and decoded message by message.

## Temporary GRIB Folder

When `grib_parameters()` runs, it creates this folder beside the input GRIB folder:

```text
20260621_00z/
|-- _tmp_grib/
`-- _tmp_param/
    |-- 0_ens/
    |-- 1_ens/
    |   |-- 10u_step0.grib
    |   |-- 10v_step0.grib
    |   |-- msl_step0.grib
    |   |-- tp_step0.grib
    |   `-- ...
    |-- 2_ens/
    `-- ...
```

Only these GRIB variables are kept:

| GRIB short name | Meaning in the workflow |
| --- | --- |
| `10u` | 10 m east-west wind component |
| `10v` | 10 m north-south wind component |
| `msl` | Mean sea-level pressure |
| `tp` | Total precipitation |

For ensemble forecasts, members `0` through `50` are processed: member `0` is the HRES reference forecast (`E1D` files) and `1`–`50` are the ENS perturbed members (`E1E` files). For deterministic mode (`is_ensemble=False`), only member `0` is processed.

## NetCDF Output

The layout depends on the `type` argument.

### `type="cosmos"`

When `loadgrib()` runs, it creates one folder per ensemble member in `base_dir`:

```text
20260621_00z/
|-- 0_ens/
|   |-- ecmwf_meteo.20260621_0000.nc
|   `-- ...
|-- 1_ens/
|   |-- ecmwf_meteo.20260621_0000.nc
|   |-- ecmwf_meteo.20260621_0300.nc
|   `-- ...
|-- 2_ens/
|   |-- ecmwf_meteo.20260621_0000.nc
|   |-- ecmwf_meteo.20260621_0300.nc
|   `-- ...
|-- ...
`-- _tmp_param/
```

Each NetCDF file contains one forecast time for one ensemble member.

### `type="schism"`

`loadgrib()` writes one file per member directly in `base_dir`, holding every forecast time:

```text
20260621_00z/
|-- ECMWF_surf_202606210000_0.nc
|-- ECMWF_surf_202606210000_1.nc
|-- ...
`-- ECMWF_surf_202606210000_50.nc
```

The pattern is `<name>_<init YYYYMMDDHHMM>_<member>.nc`. Dimensions are `(time, lat, lon)` with latitude descending, and the variables keep their GRIB-style names (`10u`, `10v`, `msl`, `precipitation`). See [`grib_decoder.py`](../modules/grib_decoder.md#schism-_write_schism) for the full format.

If `adapt_ens=True`, the `<member>_ens/` folders above are written as well, because the ranking stages read that layout. `clean_up` removes them at the end when `delete_tmp_folders=True`.

### Timing

For a Day 0 to Day 5 forecast range, the GRIB parameter-splitting stage usually takes about `30 seconds`, while the NetCDF writing stage usually takes about `1 minute`.

## 50th Percentile Output Folder

After the ensemble NetCDF files are available, `make_50th_percentile(base_dir).make_50th_percentile()` reads all folders in `base_dir` whose names end with `_ens`.

It groups files by matching NetCDF filename, computes the median across ensemble members for each variable, and writes the output to:

```text
20260621_00z/
|-- 1_ens/
|-- 2_ens/
|-- ...
`-- _adapt/
    `-- _50th_percentile/
        |-- ecmwf_meteo.20260621_0000.nc
        |-- ecmwf_meteo.20260621_0300.nc
        `-- ...
```

The output filenames match the input timestep filenames. Each output file contains the 50th percentile value for every data variable and grid cell at that timestep.

## Fraction Output Folder

After `_adapt/_50th_percentile` exists, `MakeFraction(base_dir).compute_fraction()` reads every ensemble NetCDF file and finds the matching threshold file by filename.

For each ensemble file, it computes fraction fields for:

| Variable | Neighborhood half-widths |
| --- | --- |
| `barometric_pressure` | `L1`, `L3`, `L5` |
| `wind_u` | `L1`, `L3`, `L5` |
| `wind_v` | `L1`, `L3`, `L5` |

The output is written by ensemble member:

```text
20260621_00z/
`-- _adapt/
    |-- _50th_percentile/
    `-- _fraction/
        |-- 1_ens/
        |   |-- ecmwf_meteo.20260621_0000.nc
        |   |-- ecmwf_meteo.20260621_0300.nc
        |   `-- ...
        |-- 2_ens/
        `-- ...
```

Each fraction file keeps the same timestep filename as the source ensemble file.

## Output Variables

In the CoSMoS layout, the module renames GRIB/xarray variables before writing NetCDF:

| Source name | Output name |
| --- | --- |
| `latitude` | `lat` |
| `longitude` | `lon` |
| `u10` | `wind_u` |
| `v10` | `wind_v` |
| `msl` | `barometric_pressure` |
| `tp` | `precipitation` |

In the SCHISM layout, only `latitude`/`longitude` become `lat`/`lon` and `u10`/`v10` become `10u`/`10v`; `msl` keeps its name.

The `tp` field is cumulative total precipitation in GRIB. In both layouts, the module converts it into a precipitation rate (mm/h) named `precipitation`, by differencing consecutive forecast steps, dividing by the step duration in hours, and multiplying by `1000.0`.

## Cleanup Behavior

The `delete_tmp_folders` option controls cleanup:

| Method | Cleanup when `delete_tmp_folders=True` |
| --- | --- |
| `grib_parameters()` | Deletes the original `_tmp_grib` folder. |
| `loadgrib()` | Deletes the generated `_tmp_param` folder. |
| `clean_up.run()` | Deletes `_adapt`, and for `type="schism"` also the `*_ens` folders. |

Use `delete_tmp_folders=False` while checking outputs or debugging.
