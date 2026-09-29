# AdaptEns

`AdaptEns` — *Adaptive Selection of ECMWF Ensemble using FSS displacement ranking* — prepares ECMWF ensemble meteorological forcing and ranks the ensemble members by how representative each one is of the ensemble consensus.

The pipeline converts ECMWF GRIB files into NetCDF forcing files for CoSMoS or SCHISM. When ranking is requested, it then builds a 50th-percentile threshold, computes neighborhood fractions, scores each member pair with the Fraction Skill Score (FSS), turns that into a displacement, and ranks members from most to least representative.

It processes 51 members: member `0` is the HRES reference forecast (`E1D` files) and members `1`–`50` are the ENS perturbed members (`E1E` files). With `is_ensemble=False`, only member `0` is processed.

## Pipeline at a glance

The whole workflow runs from one call to `run_adapt_ens()`, which launches `runner.bat`. The stages run in order, each consuming the previous stage's output. Stage 1 always runs; stages 2–7 run only when `adapt_ens=True`.

| # | Module | What it does |
| --- | --- | --- |
| 1 | [`grib_decoder.py`](modules/grib_decoder.md) | Decode raw GRIB into NetCDF: per-member, per-time files (`0_ens/`, `1_ens/`, …) for CoSMoS, or one file per member for SCHISM. |
| 2 | [`make_threshold.py`](modules/make_threshold.md) | Compute the 50th-percentile (median) field across members → `_adapt/_50th_percentile`. |
| 3 | [`compute_fraction.py`](modules/compute_fraction.md) | Neighborhood event fractions per member vs. the threshold → `_adapt/_fraction`. |
| 4 | [`make_fss_disp.py`](modules/make_fss_disp.md) | Pairwise FSS → displacement `d = (1 - FSS)(2L+1)` → `_adapt/_fss_disp`. |
| 5 | [`get_mean_displacement.py`](modules/get_mean_displacement.md) | Mean displacement per member per variable → `_adapt/_mean_disp`. |
| 6 | [`rank_ensemble.py`](modules/rank_ensemble.md) | Total displacement per member, ranked → `_adapt/ens_ranked.json`. |
| 7 | [`clean_up.py`](modules/clean_up.md) | Move `ens_ranked.json` up to the cycle folder, remove `_adapt` (and the `*_ens` working folders for SCHISM). |

The orchestrator itself is documented in [`runner.py`](modules/runner.md).

Python files whose names start with `_` (for example `_inspect_netcdf.py`, `_read_npz.py`) are temporary or exploratory helpers and are intentionally not documented here.

## Run the whole pipeline

```python
from AdaptEns import runner

runner.run_adapt_ens(
    path=r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z",
    is_ensemble=True,
    delete_tmp_folders=True,
    name="ecmwf_meteo",
    compute_timestep="ALL",
    adapt_ens=True,      # False: decode only, no ranking
    type="cosmos",       # or "schism"
)
```

| `type` | Output |
| --- | --- |
| `cosmos` | `<member>_ens/<name>.YYYYMMDD_HHMM.nc`, one file per timestep. |
| `schism` | `<name>_<YYYYMMDDHHMM>_<member>.nc`, one file per member (e.g. `ECMWF_surf_202607010600_0.nc`). |

See [`runner.py`](modules/runner.md) for the full argument reference and how each argument reaches the individual stages.

## Run a single stage

Every stage is also runnable on its own — as a module from the command line, or as an imported class. Each stage takes the same forecast-cycle folder (`base_dir`); the ranking stages also take a `compute_timestep` selector (`"ALL"` or the first `N` timesteps).

```python
from AdaptEns.grib_decoder import decode_Grib
from AdaptEns.make_threshold import make_50th_percentile
from AdaptEns.compute_fraction import MakeFraction

base = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

decoder = decode_Grib(
    base,                 # reads raw GRIB from <base>\_tmp_grib
    is_ensemble=True,
    delete_tmp_folders=False,
    name="ecmwf_meteo",
    type="cosmos",
)
decoder.grib_parameters()
decoder.loadgrib()

make_50th_percentile(base).make_50th_percentile()
MakeFraction(base, compute_timestep="ALL").compute_fraction()
```

Or from the command line (the form `runner.bat` uses):

```bash
python -m AdaptEns.grib_decoder          "<base_dir>" "True" "True" "ecmwf_meteo" "cosmos" "True"
python -m AdaptEns.make_threshold        "<base_dir>" "ALL"
python -m AdaptEns.compute_fraction      "<base_dir>" "ALL"
python -m AdaptEns.make_fss_disp         "<base_dir>" "ALL"
python -m AdaptEns.get_mean_displacement "<base_dir>" "ALL"
python -m AdaptEns.rank_ensemble         "<base_dir>" "ALL"
python -m AdaptEns.clean_up              "<base_dir>" "True" "cosmos"
```

## Build the docs locally

From the `AdaptEns` folder:

```bash
mkdocs serve
```
