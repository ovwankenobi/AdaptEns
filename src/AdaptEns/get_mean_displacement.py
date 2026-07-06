# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com

Compiles the per-member mean displacement  per variable from the pairwise
FSS-displacement tensors in _fss_disp:

    d_i = sum_L sum_(j != i) d_{i,j,L} / (N_L * (N_ens - 1))

for each ensemble member i and each atmospheric variable.
"""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np
from tqdm import tqdm

_KEY_RE = re.compile(r"^(.*)_L(\d+)$")


def _group_keys_by_var(keys: list[str]) -> dict[str, list[int]]:
    """
    Maps each variable name to the column indices (into the displacement
    tensor's key axis) belonging to that variable, in first-seen order.
    """
    groups: dict[str, list[int]] = {}
    for idx, key in enumerate(keys):
        m = _KEY_RE.match(str(key))
        if not m:
            continue
        groups.setdefault(m.group(1), []).append(idx)
    return groups


class get_mean_displacement:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)

        self.fss_dir = self.base_dir / "_adapt" / "_fss_disp"
        self.mean_disp = self.base_dir / "_adapt" / "_mean_disp"
        self.mean_disp.mkdir(parents=True, exist_ok=True)

    def compute(self):
        """
        Calculates the mean displacement per member, per variable:

            d_i = sum_L sum_(j != i) d_{i,j,L} / (N_L * (N_ens - 1))

        for every forecast-time NPZ file in _fss_disp, saving one NPZ per
        forecast time into _mean_disp.
        """
        npz_files = sorted(self.fss_dir.glob("*.npz"))

        if not npz_files:
            print(f"No NPZ files found in {self.fss_dir}")
            return

        for npz_file in tqdm(npz_files, desc="Mean displacement", unit="timestep"):
            data = np.load(npz_file, allow_pickle=False)

            displacement = data["displacement"]  # (n_ens, n_ens, n_keys)
            ensembles = data["ensembles"]
            keys = data["keys"]

            n_ens = displacement.shape[0]
            if n_ens < 2:
                tqdm.write(f"[WARN] {npz_file.name}: fewer than 2 members, skipping")
                continue

            groups = _group_keys_by_var(list(keys))
            if not groups:
                tqdm.write(f"[WARN] {npz_file.name}: no '<var>_L<N>' keys found")
                continue

            variables = list(groups.keys())
            n_vars = len(variables)

            total = np.empty((n_ens, n_vars), dtype=np.float32)
            for v_idx, var in enumerate(variables):
                col_idx = groups[var]
                n_l = len(col_idx)
                # d_{i,i,L} == 0 (self-comparison), so summing over all j
                # is equivalent to summing over j != i.
                summed = displacement[:, :, col_idx].sum(axis=(1, 2))
                total[:, v_idx] = summed / np.float32(n_l * (n_ens - 1))

            np.savez(
                self.mean_disp / npz_file.name,
                mean_displacement=total,
                ensembles=ensembles,
                variables=np.array(variables),
            )


if __name__ == "__main__":
    path = (
        r"D:\rsderamos\Operational_06_18_2026\Operations"
        r"\meteo_database\ecmwf_meteo\20260701_18z"
    )

    get_mean_displacement(path).compute()
