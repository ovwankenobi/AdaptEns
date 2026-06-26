# Input and Output Folder Structure

`grib_decoder.py` expects a folder containing ECMWF GRIB files. The parent folder of that GRIB input folder becomes the working directory for temporary files and NetCDF outputs. `make50thpercentile.py` then reads those ensemble NetCDF output folders and writes median products under `_adapt`.

## Input Folder

The input path is passed to `decode_Grib(path_gribfolder=...)`.

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
| `path_gribfolder` | `...\20260621_00z\_tmp_grib` |
| `base_dir` | `...\20260621_00z` |

The module reads every file directly inside `path_gribfolder`. The filenames are not interpreted by the code; each file is opened as a GRIB stream and decoded message by message.

## Temporary GRIB Folder

When `grib_parameters()` runs, it creates this folder beside the input GRIB folder:

```text
20260621_00z/
|-- _tmp_grib/
`-- _tmp_param/
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

For ensemble forecasts, members `1` through `50` are processed. For deterministic mode, only perturbation number `50` is processed.

## NetCDF Output Folders

When `loadgrib()` runs, it creates one folder per ensemble member in `base_dir`:

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
|-- ...
`-- _tmp_param/
```

Each NetCDF file contains one forecast time for one ensemble member.

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

## Output Variables

The module renames GRIB/xarray variables before writing NetCDF:

| Source name | Output name |
| --- | --- |
| `latitude` | `lat` |
| `longitude` | `lon` |
| `u10` | `wind_u` |
| `v10` | `wind_v` |
| `msl` | `barometric_pressure` |
| `tp` | `precipitation` |

The `tp` field is cumulative total precipitation in GRIB. The module converts it into a precipitation rate by differencing consecutive forecast steps, dividing by the step duration in hours, and multiplying by `1000.0`.

## Cleanup Behavior

The `delete_tmp_folders` option controls cleanup:

| Method | Cleanup when `delete_tmp_folders=True` |
| --- | --- |
| `grib_parameters()` | Deletes the original `path_gribfolder`. |
| `loadgrib()` | Deletes the generated `_tmp_param` folder. |

Use `delete_tmp_folders=False` while checking outputs or debugging.
