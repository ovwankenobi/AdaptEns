# check_netcdf_dims.py
import sys
import os
import xarray as xr


def inspect_netcdf(nc_path):
    if not os.path.exists(nc_path):
        print(f"[ERROR] File not found: {nc_path}")
        return

    try:
        ds = xr.open_dataset(nc_path)

        print("=" * 60)
        print(f"FILE: {nc_path}")
        print("=" * 60)

        # Dimensions
        print("\n[DIMENSIONS]")
        for dim_name, dim_size in ds.dims.items():
            print(f"{dim_name}: {dim_size}")

        # Coordinates
        print("\n[COORDINATES]")
        if ds.coords:
            for coord_name in ds.coords:
                print(f"{coord_name}: shape={ds[coord_name].shape}")
        else:
            print("No coordinates found")

        # Variables
        print("\n[DATA VARIABLES]")
        if ds.data_vars:
            for var in ds.data_vars:
                print(f"{var}: shape={ds[var].shape}, dtype={ds[var].dtype}")
        else:
            print("No data variables found")

        # Attributes
        print("\n[GLOBAL ATTRIBUTES]")
        if ds.attrs:
            for key, value in ds.attrs.items():
                print(f"{key}: {value}")
        else:
            print("No global attributes")

        ds.close()

    except Exception as e:
        print(f"[ERROR] Failed to open NetCDF: {e}")


if __name__ == "__main__":
    nc_path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\1_ens\ecmwf_meteo.20260621_0300.nc"
    inspect_netcdf(nc_path)