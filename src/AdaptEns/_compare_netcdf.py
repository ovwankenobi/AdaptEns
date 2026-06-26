import xarray as xr
import numpy as np

file1 = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\49_ens\ecmwf_meteo.20260621_0300.nc"
file2 = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\50_ens\ecmwf_meteo.20260621_0300.nc"

ds1 = xr.open_dataset(file1)
ds2 = xr.open_dataset(file2)

print("\n=== DIMENSIONS ===")
print("File 1:", dict(ds1.dims))
print("File 2:", dict(ds2.dims))

print("\n=== VARIABLES ===")

vars1 = set(ds1.data_vars)
vars2 = set(ds2.data_vars)

print("Only in file1:", vars1 - vars2)
print("Only in file2:", vars2 - vars1)

common_vars = vars1.intersection(vars2)

for var in sorted(common_vars):
    print(f"\n--- {var} ---")

    da1 = ds1[var]
    da2 = ds2[var]

    # Check shape
    if da1.shape != da2.shape:
        print(f"Shape differs: {da1.shape} vs {da2.shape}")
        continue

    # Compute difference
    diff = da1 - da2

    max_abs_diff = float(np.nanmax(np.abs(diff.values)))
    mean_abs_diff = float(np.nanmean(np.abs(diff.values)))

    identical = np.allclose(
        da1.values,
        da2.values,
        equal_nan=True
    )

    print(f"Identical: {identical}")
    print(f"Max abs diff: {max_abs_diff}")
    print(f"Mean abs diff: {mean_abs_diff}")

ds1.close()
ds2.close()