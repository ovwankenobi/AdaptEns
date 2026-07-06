# `get_mean_displacement.py`

`get_mean_displacement.py` reduces the pairwise displacement tensors from `_adapt/_fss_disp` into a **per-member, per-variable mean displacement** for each forecast time.

For each ensemble member `i` and variable, it averages that member's displacement against every other member across all neighborhood sizes `L`:

```text
d_i = sum_L sum_(j != i) d_{i,j,L} / (N_L * (N_ens - 1))
```

Because self-comparisons are `0`, summing over all `j` is equivalent to summing over `j != i`.

**Pipeline position:** stage 5 of 7. Run it after [`make_fss_disp.py`](make_fss_disp.md) and before [`rank_ensemble.py`](rank_ensemble.md).

## How to use the module

### Command line

```bash
python -m AdaptEns.get_mean_displacement "<base_dir>" "<compute_timestep>"
```

| Argument | Meaning |
| --- | --- |
| `<base_dir>` | Forecast-cycle folder containing `_adapt/_fss_disp/`. |
| `<compute_timestep>` | `ALL`, or an integer `N` for the first `N` timesteps. |

### As an imported class

```python
from AdaptEns.get_mean_displacement import get_mean_displacement

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

get_mean_displacement(path, compute_timestep="ALL").compute()
```

## `get_mean_displacement`

### Constructor

```python
get_mean_displacement(base_dir, compute_timestep="ALL")
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder. Reads `_adapt/_fss_disp`, writes `_adapt/_mean_disp`. |
| `compute_timestep` | `"ALL"` or first `N` timesteps. |

### `compute()`

For every `_fss_disp/<timestep>.npz`:

1. Loads `displacement` `(n_ens, n_ens, n_keys)`, `ensembles`, and `keys`.
2. Skips the file if fewer than 2 members are present.
3. Groups the `<var>_L<N>` keys by variable (`_group_keys_by_var`).
4. Sums displacement over the pairing axis and over each variable's `L` columns, then divides by `N_L * (N_ens - 1)`.
5. Writes one NPZ per forecast time to `_adapt/_mean_disp/<timestep>.npz`.

## Output NPZ contents

Each `_mean_disp/<timestep>.npz` holds:

| Array | Shape | Meaning |
| --- | --- | --- |
| `mean_displacement` | `(n_ens, n_vars)` | Mean displacement per member per variable. |
| `ensembles` | `(n_ens,)` | Member folder names. |
| `variables` | `(n_vars,)` | Variable names, e.g. `barometric_pressure`, `wind_u`, `wind_v`. |

## Helper functions

| Function | Purpose |
| --- | --- |
| `_limit_timesteps(items, compute_timestep)` | `ALL` or first `N` timesteps. |
| `_group_keys_by_var(keys)` | Maps each variable name to its column indices in the key axis, in first-seen order. |

## Notes and assumptions

- Input NPZ files come from `make_fss_disp.py`; run that stage first.
- Files with fewer than 2 members, or with no `<var>_L<N>` keys, are skipped with a `[WARN]`.
- Output filenames match the input timestep filenames.
