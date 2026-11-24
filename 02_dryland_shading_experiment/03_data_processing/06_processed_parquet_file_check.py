#!/usr/bin/env python3
"""
Script to find .apsimx files containing a specific site name that don't have
corresponding .parquet files containing that site name, and to count both types.
"""

import os
from pathlib import Path
import sys

SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

APSIM_DIRECTORY = cfg.DRYLAND_APSIM_SIMULATIONS_DIR
PARQUET_DIRECTORY = cfg.DRYLAND_PROCESSED_FILES_BEFORE_BINDING_DIR
# site = sys.argv[1]

def find_site_apsimx_without_parquet(apsimx_dir, parquet_dir, site_name):
    """
    Find site-specific .apsimx files that don't have corresponding .parquet files.
    
    Args:
        apsimx_dir (str): Path to directory containing .apsimx files
        parquet_dir (str): Path to directory containing .parquet files
        site_name (str): Site name to search for (e.g., 'waikerie')
    
    Returns:
        tuple: (missing_files, apsimx_count, parquet_count)
    """
    apsimx_directory = Path(apsimx_dir)
    parquet_directory = Path(parquet_dir)
    
    # Check if directories exist
    if not apsimx_directory.exists():
        print(f"Error: APSIMX directory '{apsimx_dir}' does not exist.")
        return [], 0, 0
    
    if not parquet_directory.exists():
        print(f"Error: Parquet directory '{parquet_dir}' does not exist.")
        return [], 0, 0
    
    if not apsimx_directory.is_dir():
        print(f"Error: '{apsimx_dir}' is not a directory.")
        return [], 0, 0
        
    if not parquet_directory.is_dir():
        print(f"Error: '{parquet_dir}' is not a directory.")
        return [], 0, 0
    
    # Get all .apsimx and .parquet files containing the site name
    apsimx_files = list(apsimx_directory.glob(f"*{site_name}*.apsimx"))
    
    # Processed files are named <simulation>_full.parquet
    suffix = "_full"
    parquet_files = [f for f in parquet_directory.glob(f"*{site_name}*.parquet")
                     if f.stem.endswith(suffix)]

    # Create sets of base names for comparison
    apsimx_bases = {f.stem for f in apsimx_files}
    parquet_bases = {f.stem[:-len(suffix)] for f in parquet_files}

    # Find missing .parquet files
    missing = sorted(apsimx_bases - parquet_bases)

    return missing, len(apsimx_files), len(parquet_files)

def save_to_file(filenames, output_file):
    """
    Save the list of filenames to a text file.
    
    Args:
        filenames (list): List of base filenames
        output_file (str): Output file path
    """
    try:
        with open(output_file, 'w') as f:
            for filename in filenames:
                f.write(f"'{filename}'\n")
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Error saving to file: {e}")

def main():
    # Configuration - change these as needed
    site_name = sys.argv[1] if len(sys.argv) > 1 else "no_site_name_provided"
    apsimx_directory = APSIM_DIRECTORY
    parquet_directory = PARQUET_DIRECTORY
    output_file = f"{site_name}_missing_parquet_files.txt"
    
    print(f"Searching for site: '{site_name}'")
    print(f"APSIMX directory: {apsimx_directory}")
    print(f"Parquet directory: {parquet_directory}")
    print("=" * 80)
    
    missing_files, apsimx_count, parquet_count = find_site_apsimx_without_parquet(
        apsimx_directory, parquet_directory, site_name
    )
    
    print(f"\nTotal .apsimx files containing '{site_name}': {apsimx_count}")
    print(f"Total .parquet files containing '{site_name}': {parquet_count}")
    
    if missing_files:
        coverage_pct = ((apsimx_count - len(missing_files)) / apsimx_count * 100) if apsimx_count > 0 else 0
        print(f"\nFound {len(missing_files)} .apsimx file(s) without corresponding .parquet file(s)")
        print(f"Coverage: {apsimx_count - len(missing_files)}/{apsimx_count} = {coverage_pct:.1f}%")
        
        save_to_file(missing_files, output_file)
        
        print("\nFirst 5 examples of missing parquet files:")
        for filename in missing_files[:5]:
            print(f"  '{filename}'")
        if len(missing_files) > 5:
            print(f"  ... and {len(missing_files) - 5} more")
    else:
        print(f"\n✓ All '{site_name}' .apsimx files have corresponding .parquet files!")
        print("Perfect coverage: 100%")

if __name__ == "__main__":
    main()