# `clean_up.py`

`clean_up.py` is the final pipeline step. It promotes the ranking result out of the working tree and removes the intermediate `_adapt` folder:

```text
<base_dir>/_adapt/ens_ranked.json  ->  <base_dir>/ens_ranked.json
then delete <base_dir>/_adapt/ and everything under it
for type="schism", also delete every <base_dir>/*_ens/ folder
```

**Pipeline position:** stage 7 of 7. Run it after [`rank_ensemble.py`](rank_ensemble.md). `runner.bat` only reaches this stage when `adapt_ens` is `True`.

## How to use the module

### Command line

```bash
python -m AdaptEns.clean_up "<base_dir>" ["<delete_tmp_folders>"] ["<type>"]
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `<base_dir>` | required | Forecast-cycle folder containing `_adapt/ens_ranked.json`. |
| `<delete_tmp_folders>` | `True` | Whether to delete the temporary folders after moving the ranking out. Parsed with `_parse_bool`. |
| `<type>` | `cosmos` | Output layout of the run: `cosmos` or `schism`. |

### As an imported class

```python
from AdaptEns.clean_up import clean_up

path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"

clean_up(path, delete_tmp_folders=True, type="cosmos").run()
```

## `clean_up`

### Constructor

```python
clean_up(base_dir, delete_tmp_folders=True, type="cosmos")
```

| Parameter | Description |
| --- | --- |
| `base_dir` | Forecast-cycle folder. |
| `delete_tmp_folders` | If truthy, remove `_adapt` (and for `schism`, the `*_ens` folders) after moving the ranking. If falsy, keep them in place. |
| `type` | `"cosmos"` or `"schism"` (case-insensitive). With `"schism"`, the `*_ens` folders were only written as working input for the ranking, so they are removed too. With `"cosmos"`, they are the product and are kept. |

### `run()`

1. If `_adapt` does not exist, prints a message and returns `None` (nothing to do).
2. If `_adapt/ens_ranked.json` is missing, leaves `_adapt` in place and returns `None`.
3. Deletes any stale `<base_dir>/ens_ranked.json` from a previous run, then moves the new one up.
4. If `delete_tmp_folders` is set, removes the entire `_adapt` tree, and for `type="schism"` every `*_ens` folder in `base_dir`.
5. Returns the destination path of the moved ranking.

It is safe to call once per completed run; missing inputs are reported rather than raised.

## Helper functions

| Function | Purpose |
| --- | --- |
| `_parse_bool(value)` | Interprets strings like `"1"`, `"true"`, `"yes"`, `"y"`, `"t"` as `True`. Useful when the argument arrives as a string from the command line. |

## Notes and assumptions

- Run this after `rank_ensemble.py` has written `_adapt/ens_ranked.json`.
- When invoked from `runner.bat`, `delete_tmp_folders` and `type` arrive as the string form of the values passed to `run_adapt_ens(...)`.
- Once this stage runs with `delete_tmp_folders=True`, what remains under the cycle folder is `ens_ranked.json` plus the product files: the `*_ens` folders for `cosmos`, or the `<name>_<init>_<member>.nc` files for `schism`.
- The `*_ens` folders are only removed when `_adapt/ens_ranked.json` exists; if the ranking is missing, the method returns early and nothing is deleted.
