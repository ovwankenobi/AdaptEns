# AdaptEns

`AdaptEns` prepares ECMWF ensemble meteorological forcing for downstream operational workflows.

The current documented workflow converts ECMWF GRIB files into organized NetCDF ensemble files, then creates a 50th percentile product from those ensemble outputs.

1. Split the original GRIB messages into temporary files grouped by ensemble member, variable, and forecast step.
2. Load those temporary GRIB files with `xarray`/`cfgrib`, standardize variable names and time coordinates, then write one NetCDF file for each ensemble member and forecast time.
3. Read matching NetCDF timesteps across ensemble-member folders and write median fields to `_adapt/_50th_percentile`.

Python files whose names start with `_` are temporary or exploratory files and are intentionally not included in this documentation.

## Documented Python files

| File | Purpose |
| --- | --- |
| `src/AdaptEns/grib_decoder.py` | Decodes ECMWF GRIB forecast files and writes ensemble NetCDF outputs. |
| `src/AdaptEns/make50thpercentile.py` | Computes the 50th percentile, or median, across ensemble NetCDF outputs. |

## Quick Example

```python
from AdaptEns.grib_decoder import decode_Grib
from AdaptEns.make50thpercentile import make_50th_percentile

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
```

Run the documentation locally from the `AdaptEns` folder:

```bash
mkdocs serve
```
