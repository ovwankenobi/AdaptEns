from eccodes import (
    codes_grib_new_from_file,
    codes_release,
    codes_keys_iterator_new,
    codes_keys_iterator_delete,
    codes_keys_iterator_next,
    codes_keys_iterator_get_name,
    codes_keys_iterator_rewind
)

file_path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib\E1E06210000062100001"

from eccodes import *

file_path = r"D:\rsderamos\Operational_06_18_2026\Operations\meteo_database\ecmwf_meteo\20260621_00z\_tmp_grib\E1E06210000062100001"

perts = set()

with open(file_path, "rb") as f:

    gid = codes_grib_new_from_file(f)

    keys = [
        "shortName",
        "perturbationNumber",
        "number",
        "date",
        "dataDate",
        "time",
        "dataTime",
        "step",
        "endStep",
        "Ni",
        "Nj"
    ]

    for key in keys:
        try:
            print(f"{key}: {codes_get(gid, key)}")
        except Exception as e:
            print(f"{key}: NOT FOUND")

    codes_release(gid)

    while True:
        gid = codes_grib_new_from_file(f)
        if gid is None:
            break

        try:
            if codes_get(gid, "eps", 0) or True:  # ensemble-safe
                try:
                    p = codes_get(gid, "perturbationNumber")
                    perts.add(int(p))
                except:
                    # fallback (VERY IMPORTANT for ECMWF files)
                    try:
                        p = codes_get(gid, "number")
                        perts.add(int(p))
                    except:
                        pass
        finally:
            codes_release(gid)


print("Perturbation numbers:", sorted(perts))


    