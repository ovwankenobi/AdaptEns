# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com

Aggregates the per-timestep mean displacement (from _mean_disp) into a
single total displacement per ensemble member, then ranks members from
most to least representative (lowest to highest total displacement) and
writes the result to _adapt/ens_ranked.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import numpy as np
from tqdm import tqdm


def _limit_timesteps(items, compute_timestep):
    """
    Restrict an ordered sequence of timestep items to the requested count.

    compute_timestep = "ALL" -> keep every timestep.
    compute_timestep = 1     -> keep only the first timestep.
    compute_timestep = N     -> keep the first N timesteps.
    """
    if isinstance(compute_timestep, str) and compute_timestep.upper() == "ALL":
        return items
    return items[: int(compute_timestep)]


class rank_ensemble:
    def __init__(self, base_dir, compute_timestep: int | str = "ALL"):
        self.base_dir = Path(base_dir)

        self.mean_disp_dir = self.base_dir / "_adapt" / "_mean_disp"
        self.adapt_dir = self.base_dir / "_adapt"
        self.adapt_dir.mkdir(parents=True, exist_ok=True)
        self.out_path = self.adapt_dir / "ens_ranked.json"
        self.compute_timestep = compute_timestep

        self.ensembles: list[str] | None = None
        self.variables: list[str] | None = None
        self.total_displacement: np.ndarray | None = None

    def get_total_displacement(self):
        """
        Summing the mean displacement across every forecast time gives the
        total displacement per ensemble member, per variable:

            D_i = sum_t d_i(t)

        Reads every NPZ in _mean_disp and accumulates a running total,
        realigning members/variables by name in case their order differs
        between files.
        """
        npz_files = sorted(self.mean_disp_dir.glob("*.npz"))

        if not npz_files:
            print(f"No NPZ files found in {self.mean_disp_dir}")
            return None

        npz_files = _limit_timesteps(npz_files, self.compute_timestep)

        ensembles: list[str] | None = None
        variables: list[str] | None = None
        total: np.ndarray | None = None

        for npz_file in tqdm(npz_files, desc="Total displacement", unit="timestep"):
            data = np.load(npz_file, allow_pickle=False)

            mean_disp = data["mean_displacement"]  # (n_ens, n_vars)
            file_ensembles = [str(e) for e in data["ensembles"]]
            file_variables = [str(v) for v in data["variables"]]

            if ensembles is None:
                ensembles = file_ensembles
                variables = file_variables
                total = np.zeros((len(ensembles), len(variables)), dtype=np.float64)

            if file_ensembles != ensembles or file_variables != variables:
                e_idx = [file_ensembles.index(e) for e in ensembles]
                v_idx = [file_variables.index(v) for v in variables]
                mean_disp = mean_disp[np.ix_(e_idx, v_idx)]

            total += mean_disp

        self.ensembles = ensembles
        self.variables = variables
        self.total_displacement = total.astype(np.float32)

        return self.total_displacement

    def rank_total_displacement(self):
        """
        Ranks ensemble members by total displacement summed across all
        variables (lower = more central/representative within the
        ensemble), and writes the ranking to _adapt/ens_ranked.json.
        """
        if self.total_displacement is None:
            self.get_total_displacement()

        if self.total_displacement is None:
            return None

        overall = self.total_displacement.sum(axis=1)
        order = np.argsort(overall)

        ranking = []
        for position, mem_idx in enumerate(order, start=1):
            ranking.append({
                "rank": position,
                "ensemble": self.ensembles[mem_idx],
                "total_displacement": float(overall[mem_idx]),
                "per_variable": {
                    var: float(self.total_displacement[mem_idx, v_idx])
                    for v_idx, var in enumerate(self.variables)
                },
            })

        with open(self.out_path, "w") as f:
            json.dump(ranking, f, indent=2)

        print(f"Wrote ranking for {len(ranking)} members to {self.out_path}")
        return ranking


if __name__ == "__main__":
    """path = (
        r"D:\rsderamos\Operational_06_18_2026\Operations"
        r"\meteo_database\ecmwf_meteo\20260701_12z"
    )"""
    path = sys.argv[1]
    compute_timestep = sys.argv[2]
    ranker = rank_ensemble(path, compute_timestep = compute_timestep)
    ranker.get_total_displacement()
    ranker.rank_total_displacement()
