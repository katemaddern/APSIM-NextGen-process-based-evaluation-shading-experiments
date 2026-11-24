import re
import polars as pl
import os
from pprint import pprint
import pyarrow.parquet as pq
import sys 
from pathlib import Path

###REQUEST 250GB memory minimum 
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

os.chdir(cfg.PROCESSED_DATA_FILES_DIR)

path = cfg.PROCESSED_DATA_FILES_DIR

DROP_BASES = [
    "NH4_KGHA", "NO3_KGHA", "SOIL_WATER_PAW",
    "SOIL_WATER_PAWMM", "UREA_KGHA",
    "NBANK",
]
drop_pattern = re.compile(
    rf"^({'|'.join(map(re.escape, DROP_BASES))})(?:\(\d+\))?$"
)

files = [
    'birchip_dryland_shading_experiment_all_processed_results.parquet',
    'lakebolac_dryland_shading_experiment_all_processed_results.parquet',
    'longerenong_dryland_shading_experiment_all_processed_results.parquet',
    'millicent_dryland_shading_experiment_all_processed_results.parquet',
    'bordertown_dryland_shading_experiment_all_processed_results.parquet',
    'lameroo_dryland_shading_experiment_all_processed_results.parquet',
    'mildura_dryland_shading_experiment_all_processed_results.parquet',
    'waikerie_dryland_shading_experiment_all_processed_results.parquet',
]

full_paths = [os.path.join(path, f) for f in files]

# --- Step 1: Use pyarrow to read schemas only (no data loaded) ---
schemas = {}
for fp in full_paths:
    schemas[fp] = set(pq.read_schema(fp).names)

# Intersection of all column names
common_cols = set.intersection(*schemas.values())

# --- Report columns that are NOT in common ---
all_cols = set.union(*schemas.values())
non_common = all_cols - common_cols

if non_common:
    print("\nColumns not present in all files:")
    for fp, col_set in schemas.items():
        site_name = os.path.basename(fp)
        missing_from_site = non_common - col_set
        if missing_from_site:
            print(f"  {site_name} is MISSING: {sorted(missing_from_site)}")
        else:
            print(f"  {site_name} has all non-common cols (i.e. it's the source of extras)")
else:
    print("\nAll files share identical column sets.")

# Apply your drop filter
cols_to_keep = sorted(
    [c for c in common_cols if not drop_pattern.fullmatch(c)]
)

print("\nColumns to keep:")
pprint(cols_to_keep)
print(f"\nKeeping {len(cols_to_keep)} columns")

# --- Step 2: Write one file at a time using a ParquetWriter ---
output_path = cfg.DRYLAND_SHADED_DF_FILE_NAME

writer = None
try:
    for fp in full_paths:
        site_name = os.path.basename(fp)
        print(f"\nProcessing {site_name}...")

        table = pq.read_table(fp, columns=cols_to_keep)

        if writer is None:
            # Schema inferred from the first table
            writer = pq.ParquetWriter(output_path, table.schema, compression="zstd")

        writer.write_table(table)
        del table
        print(f"  done.")
finally:
    if writer:
        writer.close()

print("\nfinished :)")