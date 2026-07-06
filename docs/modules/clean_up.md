# `clean_up.py`

`clean_up.py` is the final pipeline step. It promotes the ranking result out of the working tree and removes the intermediate `_adapt` folder:

```text
<base_dir>/_adapt/ens_ranked.json  ->  <base_dir>/ens_ranked.json
then delete <base_dir>/_adapt/ and everything under it
```

**Pipeline position:** stage 7 of 7. Run it after [`rank_ensemble.py`](rank_ensemble.md).

## How to use the module

### Command line

```bash
python -m AdaptEns.clean_up "<base_dir>" "<delete_tmp_folders>"
```

| Argument | Meaning |
| --- | --- |
| `<base_dir>` | Forecast-cycle folder containing `_adapt/ens_ranked.json`. |
| `<delete_tmp_folders>` | Whether to delete `_adapt` after moving the ranking out. |

### As an imported class

```python
from AdaptEns.clean_up import clean_up

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

clean_up(path, delete_tmp_folders=True).run()
```

## `clean_up`

### Constructor

```python
clean_up(base_dir, delete_tmp_folders=True)
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder. |
| `delete_tmp_folders` | If truthy, remove `_adapt` after moving the ranking. If falsy, keep `_adapt` in place. |

### `run()`

1. If `_adapt` does not exist, prints a message and returns `None` (nothing to do).
2. If `_adapt/ens_ranked.json` is missing, leaves `_adapt` in place and returns `None`.
3. Deletes any stale `<base_dir>/ens_ranked.json` from a previous run, then moves the new one up.
4. If `delete_tmp_folders` is set, removes the entire `_adapt` tree.
5. Returns the destination path of the moved ranking.

It is safe to call once per completed run; missing inputs are reported rather than raised.

## Helper functions

| Function | Purpose |
| --- | --- |
| `_parse_bool(value)` | Interprets strings like `"1"`, `"true"`, `"yes"`, `"y"`, `"t"` as `True`. Useful when the argument arrives as a string from the command line. |

## Notes and assumptions

- Run this after `rank_ensemble.py` has written `_adapt/ens_ranked.json`.
- When invoked from `runner.bat`, `delete_tmp_folders` arrives as the string form of the value passed to `run_adapt_ens(...)`.
- Once this stage runs with `delete_tmp_folders=True`, only the final `ens_ranked.json` (plus the ensemble NetCDF folders) remains under the cycle folder.
