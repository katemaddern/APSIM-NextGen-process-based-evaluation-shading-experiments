import os
import sys
import time
import datetime
import duckdb
from pathlib import Path

# ================================================================
# CONFIGURATION
# ================================================================
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg

INPUT_DB_FILE_DIRECTORY = cfg.DRYLAND_APSIM_SIMULATIONS_DIR
OUTPUT_PARQUET_FILE_DIRECTORY = cfg.DRYLAND_RAW_DATA_PARQUET_DIR


def main():
    if len(sys.argv) < 2:
        print("ERROR: no site name supplied. Usage: python 01_convert_db_to_pq.py <insite>")
        sys.exit(1)

    insite = sys.argv[1]
    start_time = time.time()

    print(f"Started at: {datetime.datetime.now()}")
    print(f"Running on node: {os.environ.get('SLURMD_NODENAME', 'unknown')}")
    print(f"SLURM_ARRAY_TASK_ID: {os.environ.get('SLURM_ARRAY_TASK_ID', 'N/A')}")

    os.chdir(OUTPUT_PARQUET_FILE_DIRECTORY)

    db_path = os.path.join(INPUT_DB_FILE_DIRECTORY, f"{insite}.db")
    output_path = f"{insite}.parquet"

    if not os.path.exists(db_path):
        print(f"ERROR: Database file does not exist: {db_path}")
        sys.exit(1)

    file_size = os.path.getsize(db_path) / (1024**2)
    print(f"Path: {db_path}")
    print(f"Database file size: {file_size:.2f} MB")

    conn = None
    try:
        conn = duckdb.connect(':memory:')
        conn.execute("LOAD sqlite;")

        conn.execute(f"ATTACH '{db_path}' AS sqlite_db (TYPE sqlite, READ_ONLY true);")

        conn.execute(f"""
            COPY (
                SELECT *, '{insite}' AS SIM_FILE
                FROM sqlite_db.Report
            ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        row_count = conn.execute("SELECT COUNT(*) FROM sqlite_db.Report").fetchone()[0]
        parquet_size = os.path.getsize(output_path) / (1024**2)

        print(f"Report table has {row_count} rows")
        print(f"Output Parquet file size: {parquet_size:.2f} MB")

    except Exception as e:
        print(f"Failed to process the database: {e}")
        sys.exit(1)

    finally:
        if conn:
            conn.close()

    elapsed = time.time() - start_time
    print(f"Data saved to {insite}.parquet at {OUTPUT_PARQUET_FILE_DIRECTORY}")
    print(f"Total runtime: {elapsed:.2f} seconds")
    print(f"Ended at: {datetime.datetime.now()}")


if __name__ == "__main__":
    main()