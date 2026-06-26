# AdaptEns

`AdaptEns` prepares ECMWF ensemble meteorological forcing for downstream operational workflows.

The current documented workflow converts ECMWF GRIB files into organized NetCDF ensemble files, creates a 50th percentile threshold product, then computes neighborhood fractions for each ensemble member.

1. Split the original GRIB messages into temporary files grouped by ensemble member, variable, and forecast step.
2. Load those temporary GRIB files with `xarray`/`cfgrib`, standardize variable names and time coordinates, then write one NetCDF file for each ensemble member and forecast time.
3. Read matching NetCDF timesteps across ensemble-member folders and write median fields to `_adapt/_50th_percentile`.
4. Compare each ensemble field against the threshold field and write fraction fields to `_adapt/_fraction`.

Python files whose names start with `_` are temporary or exploratory files and are intentionally not included in this documentation.

## Documented Python files

| File | Purpose |
| --- | --- |
| `src/AdaptEns/grib_decoder.py` | Decodes ECMWF GRIB forecast files and writes ensemble NetCDF outputs. |
| `src/AdaptEns/make_threshold.py` | Computes the 50th percentile, or median, threshold across ensemble NetCDF outputs. |
| `src/AdaptEns/fraction.py` | Computes neighborhood event fractions for each ensemble file against the 50th percentile threshold. |

## Quick Example

```python
from AdaptEns.grib_decoder import decode_Grib
from AdaptEns.make_threshold import make_50th_percentile
from AdaptEns.fraction import MakeFraction

decoder = decode_Grib(
    path_gribfolder=r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib",
    is_ensemble=True,
    delete_tmp_folders=False,
)

decoder.grib_parameters()
decoder.loadgrib()

make_50th_percentile(
    r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"
).make_50th_percentile()

MakeFraction(
    r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z"
).fraction()
```

Run the documentation locally from the `AdaptEns` folder:

```bash
mkdocs serve
```
