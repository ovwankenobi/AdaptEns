# -*- coding: utf-8 -*-
"""
Created on July 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com
"""

from pathlib import Path

import subprocess

def run_adapt_ens (path, 
                   is_ensemble, 
                   delete_tmp_folders, 
                   name,
                   compute_timestep,
                   adapt_ens = False,
                   type = "cosmos"
                   ):
    # cosmos: <member>_ens/<name>.YYYYMMDD_HHMM.nc (one file per timestep)
    # schism: <name>_<YYYYMMDDHHMM>_<member>.nc (one file per member),
    #         e.g. name="ECMWF_surf" -> ECMWF_surf_201912020000_0.nc
    type = str(type).strip().lower()
    if type not in ("cosmos", "schism"):
        raise ValueError(f"type must be 'cosmos' or 'schism', got '{type}'")

    bat = Path(__file__).parent / "runner.bat"
    print (bat)
    subprocess.run([
        str(bat),
        str(path),
        str(is_ensemble),
        str(delete_tmp_folders),
        str(name),
        str(compute_timestep),
        str(adapt_ens),
        type,
    ], shell=True)
    return


if __name__ == "__main__":
    path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260701_06z"
    run_adapt_ens (path, 
                   is_ensemble = True, 
                   delete_tmp_folders = True, 
                   name = "ecmwf_meteo",
                   compute_timestep= "ALL",
                   adapt_ens = False,
                   type = "cosmos"
                   )