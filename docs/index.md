# AdaptEns

`AdaptEns` prepares ECMWF ensemble meteorological forcing for downstream operational workflows.

The current documented module is `grib_decoder.py`, which converts ECMWF GRIB files into organized NetCDF files. It does this in two main stages:

1. Split the original GRIB messages into temporary files grouped by ensemble member, variable, and forecast step.
2. Load those temporary GRIB files with `xarray`/`cfgrib`, standardize variable names and time coordinates, then write one NetCDF file for each ensemble member and forecast time.

Python files whose names start with `_` are temporary or exploratory files and are intentionally not included in this documentation.

## Documented Python files

| File | Purpose |
| --- | --- |
| `src/AdaptEns/grib_decoder.py` | Decodes ECMWF GRIB forecast files and writes ensemble NetCDF outputs. |

## Quick Example

```python
from AdaptEns.grib_decoder import decode_Grib

decoder = decode_Grib(
    path_gribfolder=r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib",
    is_ensemble=True,
    delete_tmp_folders=False,
)

decoder.grib_parameters()
decoder.loadgrib()
```

Run the documentation locally from the `AdaptEns` folder:

```bash
mkdocs serve
```
