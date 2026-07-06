# `runner.py`

`runner.py` is the top-level entry point for the `AdaptEns` pipeline. Its `run_adapt_ens()` function launches `runner.bat`, which runs every processing stage in order for a single forecast cycle folder.

Use this module when you want to run the **whole** adaptive-ensemble workflow with one call, instead of importing and calling `grib_decoder`, `make_threshold`, `compute_fraction`, and the ranking modules individually.

## `run_adapt_ens(...)`

```python
from AdaptEns import runner

runner.run_adapt_ens(
    path=r"D:\...\meteo_database\ecmwf_meteo\20260701_06z",
    is_ensemble=True,
    delete_tmp_folders=True,
    name="ecmwf_meteo",
    compute_timestep="ALL",
)
```

### Parameters

| Parameter | Type | Meaning |
| --- | --- | --- |
| `path` | `str` | Forecast cycle folder to process. This is the working directory that holds the raw GRIB input and receives all outputs. |
| `is_ensemble` | `bool` | `True` processes ensemble members `1..50`; `False` processes the deterministic member only. |
| `delete_tmp_folders` | `bool` | `True` removes temporary/intermediate folders during the run and in the final `clean_up` stage. Use `False` while inspecting outputs or debugging. |
| `name` | `str` | Output filename prefix. Currently `ecmwf_meteo`. |
| `compute_timestep` | `str` | Which forecast timesteps to process. `"ALL"` processes every timestep; otherwise a specific timestep selector. |

Every argument is converted to a string and passed positionally to `runner.bat`.

### What it does

The function locates `runner.bat` next to `runner.py` and runs it with `subprocess.run(..., shell=True)`:

```python
bat = Path(__file__).parent / "runner.bat"
subprocess.run([
    str(bat),
    str(path),
    str(is_ensemble),
    str(delete_tmp_folders),
    str(name),
    str(compute_timestep),
], shell=True)
```

The function returns `None`; results are the files written to disk by the pipeline stages.

## Pipeline stages

`runner.bat` calls each module as `python -m AdaptEns.<module>`, in this order. The table shows which arguments each stage receives.

| # | Command | Arguments passed | Purpose |
| --- | --- | --- | --- |
| 1 | `AdaptEns.grib_decoder` | `path`, `is_ensemble`, `delete_tmp_folders`, `name` | Decode raw GRIB into per-member, per-time NetCDF files. |
| 2 | `AdaptEns.make_threshold` | `path`, `compute_timestep` | Compute the 50th percentile (median) threshold across ensemble members. |
| 3 | `AdaptEns.compute_fraction` | `path`, `compute_timestep` | Compute neighborhood event fractions for each member against the threshold. |
| 4 | `AdaptEns.make_fss_disp` | `path`, `compute_timestep` | Compute the Fraction Skill Score and displacement fields. |
| 5 | `AdaptEns.get_mean_displacement` | `path`, `compute_timestep` | Compute the mean displacement per ensemble member. |
| 6 | `AdaptEns.rank_ensemble` | `path`, `compute_timestep` | Rank ensemble members by total displacement / FSS. |
| 7 | `AdaptEns.clean_up` | `path`, `delete_tmp_folders` | Remove temporary folders when `delete_tmp_folders` is set. |

### Argument mapping in `runner.bat`

The batch script maps the five positional arguments as follows:

| `.bat` token | Source argument |
| --- | --- |
| `%~1` | `path` |
| `%~2` | `is_ensemble` |
| `%~3` | `delete_tmp_folders` |
| `%~4` | `name` |
| `%~5` | `compute_timestep` |

On success the script prints `[DONE] Finished successfully.` and exits. On a non-zero exit code it prints `[ERROR] Script failed with exit code ...` and pauses.

## Typical usage in operations

`run_adapt_ens()` is called from the operational meteo configuration after the forecast data is downloaded. In `Operations/run_folder/configuration/ecmwf_meteo.py`:

```python
from AdaptEns import runner

runner.run_adapt_ens(
    path=self.forecast_path,
    is_ensemble=self.is_ensemble,
    delete_tmp_folders=False,
    name="ecmwf_meteo",
    compute_timestep="ALL",
)
```

Here `self.forecast_path` is the cycle folder (for example `.../ecmwf_meteo/20260701_06z`) and `self.is_ensemble` comes from the run configuration.

## Notes and assumptions

- The pipeline runs stages **sequentially**; each stage assumes the previous stage's outputs already exist in `path`.
- Stage 1 (`grib_decoder`) currently reads only `path` from its command-line arguments and uses its own defaults for `is_ensemble`, `delete_tmp_folders`, and `name`; the extra tokens passed by `runner.bat` are reserved for future use.
- `shell=True` and `runner.bat` make this a Windows-oriented entry point.
- To run a single stage instead of the whole pipeline, call the corresponding module directly (see the other pages under **Modules**).
