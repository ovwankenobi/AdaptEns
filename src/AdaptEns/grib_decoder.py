# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com
"""

import os
import time
import multiprocessing as mp
from tqdm import tqdm
import shutil

from eccodes import (
    codes_grib_new_from_file,
    codes_get,
    codes_write,
    codes_release
)

import pandas as pd
import xarray as xr
import numpy as np
import glob

VARS = {"tp", "10u", "10v", "msl"}


def process_file(args):
    filepath, tmp_param, is_ensemble = args

    local_outputs = {}

    try:
        with open(filepath, "rb") as fin:
            while True:
                gid = codes_grib_new_from_file(fin)
                if gid is None:
                    break

                try:
                    short_name = codes_get(gid, "shortName")
                    if short_name not in VARS:
                        continue

                    pert_num = codes_get(gid, "perturbationNumber", int)

                    if is_ensemble:
                        if pert_num < 1 or pert_num > 50:
                            continue
                    else:
                        if pert_num != 50:
                            continue

                    step = codes_get(gid, "step", int)

                    ens_folder = os.path.join(tmp_param, f"{pert_num}_ens")
                    os.makedirs(ens_folder, exist_ok=True)

                    out_path = os.path.join(
                        ens_folder,
                        f"{short_name}_step{step}.grib"
                    )

                    if out_path not in local_outputs:
                        local_outputs[out_path] = open(out_path, "wb")

                    codes_write(gid, local_outputs[out_path])

                finally:
                    codes_release(gid)

    finally:
        for f in local_outputs.values():
            f.close()

    return filepath


def _process_member(args):
    member, tmp_param, variables, name, base_dir = args

    ensemble_folder = os.path.join(tmp_param, f"{member}_ens")

    if not os.path.isdir(ensemble_folder):
        print(f"Missing folder: {ensemble_folder}")
        return member, 0

    datasets = []

    for var in variables:
        files = glob.glob(os.path.join(ensemble_folder, f"{var}_step*.grib"))

        if not files:
            continue

        loaded = []

        for file in files:
            try:
                ds = xr.open_dataset(
                    file,
                    engine="cfgrib",
                    backend_kwargs={"indexpath": ""}
                )

                step_coord = ds.coords.get("step", None)

                if step_coord is None:
                    raise ValueError(f"No GRIB step metadata in {file}")

                step_val = step_coord.values

                if np.issubdtype(step_val.dtype, np.timedelta64):
                    step_hours = int((step_val / np.timedelta64(1, "h")).item())
                else:
                    step_hours = int(step_val.item())

                ds = ds.assign_coords(step=step_hours)
                loaded.append((step_hours, ds))

            except Exception as e:
                print(f"Failed loading {file}: {e}")

        loaded.sort(key=lambda x: x[0])
        var_datasets = [x[1] for x in loaded]

        if var_datasets:
            ds_var = xr.concat(
                var_datasets,
                dim="step",
                coords="minimal",
                compat="override"
            )
            datasets.append(ds_var)

    if not datasets:
        print(f"No datasets found for ensemble {member}")
        return member, 0

    ds = xr.merge(datasets, compat="override")

    if "tp" in ds:
        tp = ds["tp"].values
        step_hours_arr = ds["tp"].step.values.astype(float)

        dt = np.diff(step_hours_arr, prepend=step_hours_arr[0])
        dt[0] = dt[1] if len(dt) > 1 else 3.0

        rain = np.zeros_like(tp)
        rain[1:] = (tp[1:] - tp[:-1]) / dt[1:, None, None] * 1000.0

        tp_rate = xr.DataArray(
            rain,
            dims=ds["tp"].dims,
            coords={**ds["tp"].coords, "step": ds["tp"].step.values},
            name="precipitation"
        )

        ds = ds.drop_vars("tp")
        ds["precipitation"] = tp_rate.fillna(0.0)

    rename_dict = {
        "latitude": "lat",
        "longitude": "lon",
        "u10": "wind_u",
        "v10": "wind_v",
        "msl": "barometric_pressure",
    }
    ds = ds.rename(rename_dict)

    init_time = pd.Timestamp(ds.coords["time"].values)
    times = init_time + pd.to_timedelta(ds.step.values, unit="h")

    ds = ds.assign_coords(time=("step", times))
    ds = ds.swap_dims({"step": "time"})
    ds = ds.sortby("lat")

    # Write one NC per timestep (suggestion #1 intentionally not applied)
    encoding = {
        var: {"zlib": True, "complevel": 1, "dtype": "float32"}
        for var in ds.data_vars
    }

    nc_path = os.path.join(base_dir, f"{member}_ens")
    os.makedirs(nc_path, exist_ok=True)

    files_written = 0
    for t in ds.time.values:
        time_string = pd.to_datetime(t).strftime("%Y%m%d_%H%M")
        filename = os.path.join(nc_path, f"{name}.{time_string}.nc")

        ds_time = ds.sel(time=t).drop_vars("time")
        ds_time.to_netcdf(filename, encoding=encoding, engine="h5netcdf")
        ds_time.close()
        files_written += 1

    ds.close()
    return member, files_written


class decode_Grib:

    def __init__(self, path_gribfolder=None,
                 is_ensemble=True,
                 delete_tmp_folders=False,
                 name = None):
        self.path_gribfolder = path_gribfolder
        self.delete_tmp_folders = delete_tmp_folders
        self.is_ensemble = is_ensemble
        self.name = name
        self.base_dir = os.path.dirname(self.path_gribfolder)

    def grib_parameters(self):

        start_time = time.time()

        self.tmp_param = os.path.join(self.base_dir, "_tmp_param")
        os.makedirs(self.tmp_param, exist_ok=True)

        grib_files = [
            os.path.join(self.path_gribfolder, f)
            for f in os.listdir(self.path_gribfolder)
        ]

        workers = max(4, mp.cpu_count() - 1)

        with mp.Pool(workers) as pool:
            list(tqdm(
                pool.imap_unordered(
                    process_file,
                    [(f, self.tmp_param, self.is_ensemble) for f in grib_files]
                ),
                total=len(grib_files),
                desc="Processing GRIB files"
            ))

        elapsed = time.time() - start_time
        print(f"Elapsed time: {elapsed//3600:.0f}h {(elapsed%3600)//60:.0f}m {elapsed%60:.2f}s")

        if self.delete_tmp_folders:
            shutil.rmtree(self.path_gribfolder, ignore_errors=True)

    def loadgrib(self):
        variables = ("10u", "10v", "msl", "tp")

        ensemble_members = list(range(1, 51)) if self.is_ensemble else [50]

        sample_folder = os.path.join(self.tmp_param, f"{ensemble_members[0]}_ens")
        n_files = len(glob.glob(os.path.join(sample_folder, "msl_step*.grib")))
        total_outputs = len(ensemble_members) * n_files

        workers = max(4, mp.cpu_count() - 1)

        with tqdm(total=total_outputs, desc="Writing NetCDF files", unit="file") as pbar:
            with mp.Pool(workers) as pool:
                for ensemble_members, files_written in pool.imap_unordered(
                    _process_member,
                    [(m, self.tmp_param, variables, self.name, self.base_dir) for m in ensemble_members]
                ):
                    pbar.update(files_written)

        if self.delete_tmp_folders:
            shutil.rmtree(self.tmp_param, ignore_errors=True)


if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib"
    a = decode_Grib(path, is_ensemble=True, name = "ecmwf_meteo")
    a.grib_parameters()
    a.loadgrib()