# `make_fss_disp.py`

`make_fss_disp.py` compiles the pairwise **Fraction Skill Score (FSS)** between every pair of ensemble members and converts it into a displacement value for each forecast time.

Each pairwise FSS is turned into a displacement immediately after it is computed, and only the displacement is stored:

```text
d = (1 - FSS) * (2L + 1)
```

**Pipeline position:** stage 4 of 7. Run it after [`compute_fraction.py`](compute_fraction.md) and before [`get_mean_displacement.py`](get_mean_displacement.md).

## How to use the module

### Command line

```bash
python -m AdaptEns.make_fss_disp "<base_dir>" "<compute_timestep>"
```

| Argument | Meaning |
| --- | --- |
| `<base_dir>` | Forecast-cycle folder containing `_adapt/_fraction/<member>_ens/`. |
| `<compute_timestep>` | `ALL`, or an integer `N` for the first `N` timesteps. |

### As an imported class

```python
from AdaptEns.make_fss_disp import DetermineFSS_displacement

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

fss = DetermineFSS_displacement(
    path,
    compute_timestep="ALL",
    max_workers=8,
    blas_threads_per_worker=1,
)
fss.compile_fractions_time()
```

## `DetermineFSS_displacement`

### Constructor

```python
DetermineFSS_displacement(
    base_dir,
    max_workers=None,
    blas_threads_per_worker=1,
    compute_timestep="ALL",
)
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder. Reads `_adapt/_fraction`, writes `_adapt/_fss_disp`. |
| `max_workers` | Number of process-pool workers (parallel forecast times in flight). Defaults to the CPU count. |
| `blas_threads_per_worker` | BLAS threads inside each worker's matmul. Keep `max_workers * blas_threads_per_worker` near your core count to avoid oversubscription. |
| `compute_timestep` | `"ALL"` or first `N` timesteps. |

The constructor discovers the `*_ens` folders under `_adapt/_fraction`, sorted naturally, and raises `RuntimeError` if none are found.

### `compile_fractions_time()`

For each forecast time (one NetCDF filename shared across all member folders), the worker:

1. Loads the fraction arrays for all members into a `(n_ens, n_keys, y, x)` stack.
2. Computes all pairwise FSS at once with a **Gram-matrix matmul** per key.
3. Converts FSS to displacement `d = (1 - FSS) * (2L + 1)`.
4. Saves one NPZ per forecast time to `_adapt/_fss_disp/<timestep>.npz`.

It prints a per-phase timing summary (`load`, `compute`, `save`) at the end.

## Output NPZ contents

Each `_fss_disp/<timestep>.npz` holds:

| Array | Shape | Meaning |
| --- | --- | --- |
| `displacement` | `(n_ens, n_ens, n_keys)` | Pairwise displacement per key. Self-comparisons (`i == i`) are `0`. |
| `ensembles` | `(n_ens,)` | Member folder names, e.g. `1_ens`. |
| `keys` | `(n_keys,)` | The 9 `<var>_L<L>` keys. |

## How the FSS is computed

For a fixed valid-data mask across ensemble members, pairwise FSS reduces to a Gram-matrix identity (`_fss_gram_all_pairs`):

```text
cross      = F @ F.T          # one BLAS matmul per key
sum_sq[i]  = sum(F[i]^2)
FSS[i,j]   = 2 * cross[i,j] / (sum_sq[i] + sum_sq[j])
```

This replaces an `n_ens`-choose-2 Python loop with one matmul per key.

> **Assumption:** the finite/invalid mask is identical for every member at a given key and forecast time (true when missingness comes from a static terrain/domain mask, not per-file corruption). `_fss_batch_reference` and the module's `validate_gram_vs_loop` notes exist to check this against the original per-pair logic before trusting it in production.

## Helper functions

| Function | Purpose |
| --- | --- |
| `_natural_sort_key(path)` | Natural (numeric-aware) sort so `2_ens` precedes `10_ens`. |
| `_limit_timesteps(items, compute_timestep)` | `ALL` or first `N` timesteps. |
| `_load_arrays(file)` | Reads the 9 keys, bypasses netCDF4 auto mask/scale, honors fill values manually, multiplies by `0.01` to undo the `int16` scaling from `compute_fraction.py`. |
| `_scale_factors(keys)` | Returns the `2L + 1` factor per key. |
| `_set_blas_threads(n)` / `_init_worker(n)` | Limit BLAS threads per worker (via `threadpoolctl`, falling back to env vars). |
| `_fss_gram_all_pairs(stack)` | Vectorized all-pairs FSS. |
| `_process_forecast_time(args)` | Full per-timestep worker: load → matmul → save NPZ. |

## Notes and assumptions

- Input fraction values are stored as `int16 * 0.01`; this module multiplies by `0.01` on read to recover the fraction.
- Output is **uncompressed** `.npz` (compression was the dominant per-file cost).
- Tune `max_workers` vs `blas_threads_per_worker` empirically: many workers / 1 thread wins for many members on small grids; fewer workers / more threads wins for large grids.
