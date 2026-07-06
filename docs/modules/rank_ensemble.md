# `rank_ensemble.py`

`rank_ensemble.py` aggregates the per-timestep mean displacement from `_adapt/_mean_disp` into a single **total displacement** per ensemble member, then ranks members from most to least representative and writes the result to `_adapt/ens_ranked.json`.

Lower total displacement means a member sits closer to the ensemble consensus, so it ranks higher (rank 1 = most representative).

```text
D_i = sum_t d_i(t)          # total displacement per member
```

**Pipeline position:** stage 6 of 7. Run it after [`get_mean_displacement.py`](get_mean_displacement.md) and before [`clean_up.py`](clean_up.md).

## How to use the module

### Command line

```bash
python -m AdaptEns.rank_ensemble "<base_dir>" "<compute_timestep>"
```

| Argument | Meaning |
| --- | --- |
| `<base_dir>` | Forecast-cycle folder containing `_adapt/_mean_disp/`. |
| `<compute_timestep>` | `ALL`, or an integer `N` for the first `N` timesteps. |

### As an imported class

```python
from AdaptEns.rank_ensemble import rank_ensemble

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

ranker = rank_ensemble(path, compute_timestep="ALL")
ranker.get_total_displacement()
ranker.rank_total_displacement()
```

Call `get_total_displacement()` before `rank_total_displacement()`. (If you skip it, `rank_total_displacement()` calls it for you.)

## `rank_ensemble`

### Constructor

```python
rank_ensemble(base_dir, compute_timestep="ALL")
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder. Reads `_adapt/_mean_disp`, writes `_adapt/ens_ranked.json`. |
| `compute_timestep` | `"ALL"` or first `N` timesteps. |

### `get_total_displacement()`

Reads every NPZ in `_mean_disp` and accumulates a running total per member per variable. It realigns members and variables **by name** in case their order differs between files. Stores the result on `self.total_displacement` `(n_ens, n_vars)` and returns it.

### `rank_total_displacement()`

1. Sums total displacement across all variables to get one score per member.
2. Sorts members ascending (`np.argsort`) — lowest displacement first.
3. Writes `_adapt/ens_ranked.json` and returns the ranking list.

## Output — `ens_ranked.json`

A JSON list, ordered best rank first:

```json
[
  {
    "rank": 1,
    "ensemble": "7_ens",
    "total_displacement": 12.34,
    "per_variable": {
      "barometric_pressure": 4.10,
      "wind_u": 3.90,
      "wind_v": 4.34
    }
  }
]
```

`clean_up.py` later moves this file up to `<base_dir>/ens_ranked.json`.

## Helper functions

| Function | Purpose |
| --- | --- |
| `_limit_timesteps(items, compute_timestep)` | `ALL` or first `N` timesteps. |

## Notes and assumptions

- Input NPZ files come from `get_mean_displacement.py`; run that stage first.
- Ranking is by displacement summed across all variables, with equal weighting.
- Members and variables are matched by name across files, so inconsistent ordering between timesteps is handled safely.
