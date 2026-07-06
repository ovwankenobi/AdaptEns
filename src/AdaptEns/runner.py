
from pathlib import Path

import subprocess

def run_adapt_ens (path, 
                   is_ensemble, 
                   delete_tmp_folders, 
                   name,
                   compute_timestep,
                   ):
    bat = Path(__file__).parent / "runner.bat"
    print (bat)
    subprocess.run([
        str(bat),
        str(path),
        str(is_ensemble),
        str(delete_tmp_folders),
        str(name),
        str(compute_timestep),
    ], shell=True)
    return


if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"
    run_adapt_ens (path, 
                   is_ensemble = True, 
                   delete_tmp_folders = True, 
                   name = "ecmwf_meteo",
                   compute_timestep= "ALL",
                   )