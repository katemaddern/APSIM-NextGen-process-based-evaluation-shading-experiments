import os
import sys
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

ROW_GROUP_ROWS = 100_000   # rows per row group (keeps the Parquet footer small)
READ_ATTEMPTS = 4          # retries for transient network-filesystem errors
CHUNK = 500                # files read in parallel per batch


def read_file(path):
    for i in range(READ_ATTEMPTS):
        try:
            return pq.read_table(path, use_threads=False)
        except OSError:
            if i == READ_ATTEMPTS - 1:
                raise
            time.sleep(2 * (i + 1))


def check_schema(table, schema, path):
    if table.schema.equals(schema, check_metadata=False):
        return
    expected = {f.name: f.type for f in schema}
    got = {f.name: f.type for f in table.schema}
    diffs = [f"{c}: expected {expected.get(c)}, got {got.get(c)}"
             for c in sorted(expected.keys() | got.keys())
             if expected.get(c) != got.get(c)]
    raise ValueError(f"Schema mismatch in {os.path.basename(path)}:\n  "
                     + "\n  ".join(diffs[:50]))


def combine_day_files(db_dir, insite, output_path, filters=None, n_workers=8):
    files = sorted(
        os.path.join(db_dir, f) for f in os.listdir(db_dir)
        if f.endswith(".parquet")
        and insite.lower() in f.lower()
        # and "full" in f.lower()
        and "all" not in f.lower()
        and (not filters or all(flt in f for flt in filters))
    )
    print(f"Found {len(files)} files to process")
    if not files:
        return

    schema = read_file(files[0]).schema
    print(f"Schema: {len(schema)} columns (from {os.path.basename(files[0])})")

    total_rows = 0
    buffer, buffered_rows = [], 0

    with pq.ParquetWriter(output_path, schema, compression="zstd") as writer, \
         ThreadPoolExecutor(max_workers=n_workers) as executor:
        for start in range(0, len(files), CHUNK):
            chunk = files[start:start + CHUNK]
            for path, table in zip(chunk, executor.map(read_file, chunk)):
                check_schema(table, schema, path)
                buffer.append(table)
                buffered_rows += table.num_rows
                if buffered_rows >= ROW_GROUP_ROWS:
                    writer.write_table(pa.concat_tables(buffer))
                    total_rows += buffered_rows
                    buffer, buffered_rows = [], 0
            print(f"  {min(start + CHUNK, len(files))}/{len(files)} files processed...")

        if buffer:
            writer.write_table(pa.concat_tables(buffer))
            total_rows += buffered_rows

    print(f"Wrote {total_rows:,} rows from {len(files)} files to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python script.py <insite> [filter1 filter2 ...]")

    print("Started:", datetime.datetime.now())
    t0 = time.time()

    insite = sys.argv[1]
    filters = sys.argv[2:] or None
    out_dir = cfg.SHADING_PROCESSED_FILES_FOR_ANALYSIS_DIR
    os.makedirs(out_dir, exist_ok=True)

    combine_day_files(cfg.SHADING_RAW_DATA_PARQUET_DIR, insite,
                      os.path.join(out_dir, f"{insite}_all_rows_no_processing.parquet"), filters)

    print(f"Total runtime: {time.time() - t0:.2f}s")
    print("Ended:", datetime.datetime.now())