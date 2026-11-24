#!/usr/bin/env python3
"""
For a given site, finds all matching .parquet files in the search directory
and writes a summary of each file's Report table shape (rows x cols) to
an output file. Used to verify that APSIM simulations ran properly.

Usage:
    python 4_check_parquet_shapes.py <site> [--expected-rows N] [--max-rows N]

sbatch array usage:
    sbatch --array=0-N submit_jobs.sh sites.txt
"""

import argparse
import os
import sqlite3
import statistics
import sys
from pathlib import Path
import pyarrow.parquet as pq

SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

SEARCH_DIRECTORY = cfg.SHADING_RAW_DATA_PARQUET_DIR


def get_report_shape(parquet_path: Path):
    """Return (n_rows, n_cols) for the Parquet file, or an error string."""
    try:
        md = pq.read_metadata(parquet_path)
        return md.num_rows, md.num_columns, None
    except FileNotFoundError as e:
        return None, None, f"file not found: {e}"
    except (OSError, pq.ArrowInvalid) as e:
        return None, None, f"parquet error: {e}"
    except UnicodeDecodeError as e:
        return None, None, f"unicode error in path: {e}"
    except Exception as e:
        return None, None, f"unexpected error: {e}"


def classify(n_rows, expected_rows, max_rows):
    """Return a warning tag if the row count looks wrong, else empty string."""
    if n_rows == 0:
        return "WARN: zero rows"
    if expected_rows is not None and n_rows < expected_rows:
        return f"WARN: only {n_rows} rows, expected {expected_rows}"
    if max_rows is not None and n_rows > max_rows:
        return f"WARN: {n_rows} rows exceeds max {max_rows}"
    return ""


def percentile(sorted_data, p):
    """Nearest-rank percentile from a pre-sorted list."""
    n = len(sorted_data)
    idx = max(0, min(n - 1, round(p / 100 * n) - 1))
    return sorted_data[idx]


def main():
    parser = argparse.ArgumentParser(
        description="Check Report table shapes in APSIM .parquet files for a site."
    )
    parser.add_argument("site", help="Site name to filter .parquet files")
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=None,
        metavar="N",
        help="Flag files whose Report table has fewer than N rows",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        metavar="N",
        help="Flag files whose Report table has more than N rows",
    )
    args = parser.parse_args()

    site = args.site
    expected_rows = args.expected_rows
    max_rows = args.max_rows
    directory = Path(SEARCH_DIRECTORY)
    output_file = Path(f"report_raw_parquet_shapes_{site}.txt")

    if not directory.exists() or not directory.is_dir():
        print(f"Error: '{SEARCH_DIRECTORY}' not found or is not a directory.")
        sys.exit(1)

    parquet_files = sorted(directory.glob(f"*{site}*.parquet"))

    if not parquet_files:
        print(f"No .parquet files found for site '{site}' in {SEARCH_DIRECTORY}")
        sys.exit(0)

    print(f"Found {len(parquet_files)} .parquet files for site '{site}'")
    if expected_rows is not None:
        print(f"Expected rows per file (minimum): {expected_rows}")
    if max_rows is not None:
        print(f"Maximum rows per file: {max_rows}")
    print(f"Writing results to {output_file}")

    results = []  # (parquet_path, n_rows, n_cols, err, tag)

    with open(output_file, "w") as f:
        # Write header
        f.write(f"# Report table shapes for site: {site}\n")
        f.write(f"# Directory: {SEARCH_DIRECTORY}\n")
        if expected_rows is not None:
            f.write(f"# Minimum expected rows: {expected_rows}\n")
        if max_rows is not None:
            f.write(f"# Maximum allowed rows: {max_rows}\n")
        f.write(f"# {'filename':<70} {'rows':>8}  {'cols':>5}  note\n")
        f.write("-" * 100 + "\n")

        # Process and write each file incrementally so partial output is
        # preserved if something goes wrong mid-run
        for i, parquet_path in enumerate(parquet_files, 1):
            n_rows, n_cols, err = get_report_shape(parquet_path)
            tag = "" if err else classify(n_rows, expected_rows, max_rows)
            results.append((parquet_path, n_rows, n_cols, err, tag))

            if err:
                f.write(f"  {parquet_path.name:<70} {'':>8}  {'':>5}  ERROR: {err}\n")
            else:
                f.write(f"  {parquet_path.name:<70} {n_rows:>8}  {n_cols:>5}  {tag}\n")

            # Flush periodically so output is visible during long runs
            if i % 500 == 0:
                f.flush()
                print(f"  Progress: {i}/{len(parquet_files)} files processed...")

        # Summary footer
        errors   = [(r[0].name, r[3]) for r in results if r[3]]
        warnings = [(r[0].name, r[4]) for r in results if not r[3] and r[4]]
        row_counts = sorted(r[1] if r[1] is not None else 0 for r in results)

        f.write("-" * 100 + "\n")
        f.write(
            f"# Total: {len(parquet_files)} files  |  "
            f"{len(errors)} errors  |  {len(warnings)} warnings\n"
        )

        if row_counts:
            f.write("\n# --- Row count summary (all files; errors counted as 0 rows) ---\n")
            f.write(f"#   min  : {min(row_counts)}\n")
            f.write(f"#   max  : {max(row_counts)}\n")
            f.write(f"#   mean : {statistics.mean(row_counts):.1f}\n")
            f.write("#\n")
            f.write("#   decile breakdown:\n")
            for d in range(0, 11):
                f.write(f"#     {d*10:>3}th pct : {percentile(row_counts, d*10)}\n")

    # stdout summary
    if errors:
        print(f"\n{len(errors)} file(s) with errors:")
        for name, err in errors:
            print(f"  {name}: {err}")

    if warnings:
        print(f"\n{len(warnings)} file(s) with warnings:")
        for name, tag in warnings:
            print(f"  {name}: {tag}")

    if not errors and not warnings:
        print("All files look good.")


if __name__ == "__main__":
    main()