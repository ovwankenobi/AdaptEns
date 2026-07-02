# -*- coding: utf-8 -*-
"""
Interactive NPZ FSS Browser
"""

from pathlib import Path
import numpy as np


def load_npz(npz_path):
    data = np.load(npz_path, allow_pickle=False)

    scores = data["scores"]
    ensembles = data["ensembles"]
    keys = data["keys"]

    return scores, ensembles, keys


def choose_file(npz_files):
    while True:
        print("\nAvailable forecast files:\n")

        for i, file in enumerate(npz_files, 1):
            print(f"[{i}] {file.name}")

        choice = input("\nChoose file number (q to quit): ").strip()

        if choice.lower() == "q":
            return None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(npz_files):
                return npz_files[idx]

        print("Invalid choice.")


def choose_ensemble(ensembles, label):
    while True:
        print(f"\nAvailable ensembles ({label}):\n")

        for i, ens in enumerate(ensembles, 1):
            print(f"[{i}] {ens}")

        choice = input(f"\nChoose ensemble ({label}): ").strip()

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ensembles):
                return idx

        print("Invalid choice.")


def show_scores(scores, ensembles, keys, i, j):
    print("\n" + "=" * 60)
    print(f"Comparison: {ensembles[i]} vs {ensembles[j]}")
    print("=" * 60)

    for k, key in enumerate(keys):
        score = scores[i, j, k]
        print(f"{key:30s} : {score:.6f}")

    print("=" * 60)


def main():
    folder = Path(
        input("Enter folder containing NPZ files:\n").strip()
    )

    if not folder.exists():
        print("Folder does not exist.")
        return

    npz_files = sorted(folder.glob("*.npz"))

    if not npz_files:
        print("No NPZ files found.")
        return

    while True:
        selected = choose_file(npz_files)

        if selected is None:
            break

        scores, ensembles, keys = load_npz(selected)

        i = choose_ensemble(ensembles, "A")
        j = choose_ensemble(ensembles, "B")

        show_scores(scores, ensembles, keys, i, j)

        again = input("\nInspect another pair? (y/n): ").strip().lower()
        if again != "y":
            break


if __name__ == "__main__":
    main()