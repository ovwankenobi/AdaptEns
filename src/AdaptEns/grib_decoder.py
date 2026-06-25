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

VARS = {"tp", "10u", "10v", "msl"}


# ✅ MUST BE OUTSIDE CLASS FOR MULTIPROCESSING SAFETY
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
                    pert_num = codes_get(gid, "perturbationNumber", int)

                    # ✅ MODE LOGIC
                    if is_ensemble:
                        # keep 1–50
                        if pert_num < 1 or pert_num > 50:
                            continue
                    else:
                        # keep only 50
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


class decode_Grib:

    def __init__(self, path_gribfolder=None,
                 is_ensemble=True,
                 delete_gribfolder=False):
        self.path_gribfolder = path_gribfolder
        self.delete_gribfolder = delete_gribfolder
        self.is_ensemble = is_ensemble

    def grib_parameters(self):

        start_time = time.time()

        # safer path handling
        base_dir = os.path.dirname(self.path_gribfolder)
        self.tmp_param = os.path.join(base_dir, "_tmp_param")
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
        
        if self.delete_gribfolder:
            shutil.rmtree(self.path_gribfolder, ignore_errors=True)

 


if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib"
    decode_Grib(path,is_ensemble=True).grib_parameters()