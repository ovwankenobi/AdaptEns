# -*- coding: utf-8 -*-
"""
Created on June 2026

@author: Rovie de Ramos
@email: rsderamos01@gmail.com

Final pipeline step: promotes the ranking result to the run's base
directory and removes the intermediate _adapt working tree.

    <base_dir>/_adapt/ens_ranked.json  ->  <base_dir>/ens_ranked.json

then deletes <base_dir>/_adapt and everything under it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
import sys

class clean_up:
    def __init__(self, base_dir, delete_tmp_folders=True):
        self.base_dir = Path(base_dir)
        self.delete_tmp_folders = delete_tmp_folders

        self.adapt_dir = self.base_dir / "_adapt"
        self.src_path = self.adapt_dir / "ens_ranked.json"
        self.dst_path = self.base_dir / "ens_ranked.json"

    def run(self):
        """
        Moves ens_ranked.json out of _adapt into the base directory, then
        removes the _adapt directory when delete_tmp_folders is True. Safe to
        call once per completed run; missing inputs are reported rather than
        raised.
        """
        if not self.adapt_dir.exists():
            print(f"Nothing to clean: {self.adapt_dir} does not exist")
            return None

        if not self.src_path.exists():
            print(f"Ranking not found, leaving _adapt in place: {self.src_path}")
            return None

        # Replace any ranking from a previous run so the move never fails.
        if self.dst_path.exists():
            self.dst_path.unlink()
        shutil.move(str(self.src_path), str(self.dst_path))
        print(f"Moved ranking to {self.dst_path}")

        if self.delete_tmp_folders:
            shutil.rmtree(self.adapt_dir)
            print(f"Removed {self.adapt_dir}")

        return self.dst_path


def _parse_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t")


if __name__ == "__main__":
    path = sys.argv[1]
    delete_tmp_folders = sys.argv[2]
    clean_up(path, delete_tmp_folders = delete_tmp_folders).run()
