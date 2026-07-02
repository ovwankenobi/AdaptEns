
from pathlib import Path

import subprocess

def run (path):
    bat = Path(__file__).parent / "run_grib_decoder.bat"
    print (bat)
    subprocess.run([
        str(bat),
        path
    ], shell=True)
    return
