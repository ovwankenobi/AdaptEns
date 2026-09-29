# `runner.py`

`runner.py` is the top-level entry point for the `AdaptEns` pipeline. Its `run_adapt_ens()` function launches `runner.bat`, which decodes the GRIB input for one forecast cycle folder and, when asked, ranks the ensemble members.

Use this module when you want to run the whole workflow with one call, instead of importing and calling `grib_decoder`, `make_threshold`, `compute_fraction`, and the ranking modules individually.

## `run_adapt_ens(...)`

```python
from AdaptEns import runner

runner.run_adapt_ens(
    path=r"D:\...\meteo_database\ecmwf_meteo\20260701_06z",
    is_ensemble=True,
    delete_tmp_folders=True,
    name="ecmwf_meteo",
    compute_timestep="ALL",
    adapt_ens=True,
    type="cosmos",
)
```

### Parameters

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `path` | `str` | required | Forecast cycle folder to process. It must contain the raw GRIB files in `_tmp_grib/`, and it receives all outputs. |
| `is_ensemble` | `bool` | required | `True` processes members `0..50` (member `0` is the HRES reference from the `E1D` files, `1..50` are the ENS perturbed members from the `E1E` files). `False` processes member `0` only. |
| `delete_tmp_folders` | `bool` | required | `True` removes temporary folders (`_tmp_grib`, `_tmp_param`, `_adapt`, and for `schism` the `*_ens` working folders). Use `False` while inspecting outputs or debugging. |
| `name` | `str` | required | Output filename prefix, for example `ecmwf_meteo` (CoSMoS) or `ECMWF_surf` (SCHISM). |
| `compute_timestep` | `str` | required | Which forecast timesteps the ranking stages use. `"ALL"` uses every timestep; an integer `N` uses the first `N`. Ignored when `adapt_ens=False`. |
| `adapt_ens` | `bool` | `False` | `True` runs the ranking stages (2–7) after decoding and writes `ens_ranked.json`. `False` only decodes the GRIB files. |
| `type` | `str` | `"cosmos"` | Output layout: `"cosmos"` or `"schism"` (case-insensitive). Any other value raises `ValueError`. See [Output layouts](#output-layouts). |

Every argument is converted to a string and passed positionally to `runner.bat`.

### Output layouts

| `type` | Files written by `grib_decoder` | Example |
| --- | --- | --- |
| `cosmos` | One NetCDF per timestep, in one folder per member: `<member>_ens/<name>.YYYYMMDD_HHMM.nc` | `0_ens/ecmwf_meteo.20260701_0600.nc` |
| `schism` | One NetCDF per member, holding every timestep: `<name>_<YYYYMMDDHHMM>_<member>.nc` | `ECMWF_surf_202607010600_0.nc` |

The ranking stages only read the `cosmos` layout. When `type="schism"` and `adapt_ens=True`, the decoder writes both layouts: the SCHISM files are the product, and the `<member>_ens/` folders are working input for the ranking that `clean_up` removes at the end (when `delete_tmp_folders=True`).

### What it does

The function validates `type`, locates `runner.bat` next to `runner.py`, and runs it with `subprocess.run(..., shell=True)`:

```python
bat = Path(__file__).parent / "runner.bat"
subprocess.run([
    str(bat),
    str(path),
    str(is_ensemble),
    str(delete_tmp_folders),
    str(name),
    str(compute_timestep),
    str(adapt_ens),
    type,
], shell=True)
```

The function returns `None`; the results are the files written to disk.

## Pipeline stages

`runner.bat` calls each module as `python -m AdaptEns.<module>`, in this order. Stages 2–7 run only when `adapt_ens` is `True`; otherwise the script prints `[SKIP] Ranking steps skipped` after stage 1.

| # | Command | Arguments passed | Runs when | Purpose |
| --- | --- | --- | --- | --- |
| 1 | `AdaptEns.grib_decoder` | `path`, `is_ensemble`, `delete_tmp_folders`, `name`, `type`, `adapt_ens` | always | Decode raw GRIB into NetCDF in the chosen layout. |
| 2 | `AdaptEns.make_threshold` | `path`, `compute_timestep` | `adapt_ens` | 50th percentile (median) threshold across members. |
| 3 | `AdaptEns.compute_fraction` | `path`, `compute_timestep` | `adapt_ens` | Neighborhood event fractions for each member against the threshold. |
| 4 | `AdaptEns.make_fss_disp` | `path`, `compute_timestep` | `adapt_ens` | Pairwise Fraction Skill Score and displacement. |
| 5 | `AdaptEns.get_mean_displacement` | `path`, `compute_timestep` | `adapt_ens` | Mean displacement per member. |
| 6 | `AdaptEns.rank_ensemble` | `path`, `compute_timestep` | `adapt_ens` | Rank members by total displacement. |
| 7 | `AdaptEns.clean_up` | `path`, `delete_tmp_folders`, `type` | `adapt_ens` | Move `ens_ranked.json` up and remove temporary folders. |

### Argument mapping in `runner.bat`

| `.bat` token | Source argument |
| --- | --- |
| `%~1` | `path` |
| `%~2` | `is_ensemble` |
| `%~3` | `delete_tmp_folders` |
| `%~4` | `name` |
| `%~5` | `compute_timestep` |
| `%~6` | `adapt_ens` |
| `%~7` | `type` |

Note that `grib_decoder` receives `type` and `adapt_ens` in the opposite order (`"%~7" "%~6"`), matching its own command-line signature.

The ranking check is `IF /I NOT "%~6"=="True"`, so `adapt_ens` must arrive as the string `True` (case-insensitive). `str(True)` from Python satisfies this.

On success the script prints `[DONE] Finished successfully.` and exits. On a non-zero exit code it prints `[ERROR] Script failed with exit code ...` and pauses.

## Typical usage in operations

### CoSMoS

In `Operations/cosmos/run_folder/configuration/ecmwf_meteo.py`, after the forecast data is downloaded:

```python
from AdaptEns import runner

runner.run_adapt_ens(
    path=self.forecast_path,
    is_ensemble=self.is_ensemble,
    delete_tmp_folders=False,
    name="ecmwf_meteo",
    compute_timestep="ALL",
    adapt_ens=adapt_ens,
)
```

`type` is left at its default, `"cosmos"`. When `is_ensemble` is `True`, the configuration then calls `sKit_meteo.ecmwf.select_ens` to keep only a ranked subset of the `*_ens` folders. When it is `False`, it moves the files from `0_ens/` up to the forecast path.

### SCHISM

In `SCHISM/ecmwf_data.py`:

```python
runner.run_adapt_ens(
    path=self.forecast_path,
    is_ensemble=self.is_ensemble,
    delete_tmp_folders=self.delete_tmp_folders,
    name="ECMWF_surf",
    compute_timestep="ALL",
    adapt_ens=False,
    type="schism",
)
```

This writes one `ECMWF_surf_<init>_<member>.nc` per member and skips the ranking. With `adapt_ens=True` it would also write `ens_ranked.json`; the ranking does not delete any SCHISM member file.

## Notes and assumptions

- The stages run sequentially; each assumes the previous stage's outputs already exist in `path`.
- Member `0` is included in the ranking together with members `1..50`, because the ranking stages read every `*_ens` folder in `path`.
- `shell=True` and `runner.bat` make this a Windows-oriented entry point.
- To run a single stage instead of the whole pipeline, call the corresponding module directly (see the other pages under **Modules**).
