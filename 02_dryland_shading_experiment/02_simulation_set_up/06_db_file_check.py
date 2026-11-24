#!/usr/bin/env python3
"""
Script to find .apsimx files containing site names that don't have
corresponding .db files in the specified directory, for multiple sites.
"""

from pathlib import Path
import sys
import os
from pathlib import Path

# ================================================================
# CONFIGURATION
# ================================================================
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

DIRECTORY = cfg.DRYLAND_APSIM_SIMULATIONS_DIR

def load_manifest(manifest_path):
    """Read the manifest file and return a list of Path objects."""
    with open(manifest_path) as f:
        return [Path(line.strip()) for line in f if line.strip()]

LIST_OF_APSIMX_FILES = load_manifest(cfg.DRYLAND_APSIM_MANIFEST)


def find_apsimx_without_db(directory, site):
    """
    Find .apsimx files for a given site that don't have corresponding .db files.

    Args:
        directory (Path): Path object for the directory to search.
        site (str): Site name to search for.

    Returns:
        tuple: (missing_stems, apsimx_count, db_count)
    """
    apsimx_files = [Path(f) if not isinstance(f, Path) else f
                     for f in LIST_OF_APSIMX_FILES if site in Path(f).stem]
    db_files = list(directory.glob(f"*{site}*.db"))

    apsimx_bases = {f.stem for f in apsimx_files}
    db_bases = {f.stem for f in db_files}

    missing = sorted(apsimx_bases - db_bases)
    return missing, len(apsimx_files), len(db_files)


def save_to_file(missing_by_site, output_file):
    """Save the missing files grouped by site to a text file."""
    try:
        with open(output_file, 'w') as f:
            for site_name, missing in missing_by_site.items():
                if missing:
                    f.write(f"[{site_name}]\n")
                    for stem in missing:
                        f.write(f"  '{stem}'\n")
                    f.write("\n")
        print(f"\nResults saved to: {output_file}")
    except Exception as e:
        print(f"Error saving to file: {e}")


def main():
    site = sys.argv[1]
    search_directory = DIRECTORY
    output_file = f"{site}_missing_db_files.txt"

    directory = Path(search_directory)
    if not directory.exists() or not directory.is_dir():
        print(f"Error: Directory '{search_directory}' not found or is not a directory.")
        return

    print(f"Searching directory: {search_directory}")
    print("=" * 80)

    total_apsimx = 0
    total_db = 0
    total_missing = 0
    missing_by_site = {}

    missing, apsimx_count, db_count = find_apsimx_without_db(directory, site)
    missing_by_site[site] = missing
    total_apsimx += apsimx_count
    total_db += db_count
    total_missing += len(missing)

    status = f"{len(missing)} missing" if missing else "complete"
    print(f"  {site:<20} {apsimx_count:>4} .apsimx  |  {db_count:>4} .db  |  {status}")

    print("-" * 80)
    print(f"  {'TOTAL':<20} {total_apsimx:>4} .apsimx  |  {total_db:>4} .db  |  {total_missing} missing")

    if total_missing:
        print(f"\nDetails of missing .db files:")
        for site_name, missing in missing_by_site.items():
            if missing:
                print(f"\n  [{site_name}] — {len(missing)} missing:")
                for stem in missing[:5]:
                    print(f"    '{stem}'")
                if len(missing) > 5:
                    print(f"    ... and {len(missing) - 5} more")

        save_to_file(missing_by_site, output_file)
    else:
        print("\nAll .apsimx files have corresponding .db files!")


if __name__ == "__main__":
    main()