import os
import time
import datetime
import sys
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import pyarrow as pa
import pyarrow.parquet as pq

try:
    print("Script:", os.path.basename(__file__))
    print("Directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode.")

print("Started:", datetime.datetime.now())
start_time = time.time()

SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

# Rows buffered before writing one row group. Keeping the number of row groups
# small keeps the Parquet footer tiny.
ROW_GROUP_ROWS = 100_000

# Retries for transient network-filesystem errors. Waits 2s, 4s, 6s.
READ_ATTEMPTS = 4

# Abort if this many files fail before a single file succeeds (a systematic
# problem such as a bad schema, not a few bad files).
FAIL_FAST_AFTER = 20

# Number of files whose schema is read to build the unified schema, spread
# evenly across the file list (covers control and shading, all cultivars).
N_SCHEMA_SAMPLE = 1000

# Columns dropped entirely (never read from disk, not in the output).
DROP_COLS = frozenset(['NBANK'])

# Columns that are NOT forced to float64 (strings, dates, categories, etc.).
# Date/time columns (e.g. DATE_START_SHADING, DATE_MID_SHADING) keep their
# type automatically and do not need listing here.
EXCLUDE_COLS = frozenset([
    'EXPERIMENT', 'SITE', 'TOS', 'DATE', 'CULTIVAR', 'ZONE',
    'WHEAT_PHENOLOGY_CURRENTPHASENAME', 'WHEAT_PHENOLOGY_CURRENTSTAGENAME',
    'SIM_FILE', 'NBANK_AMOUNT', 'FERTDATE_DOY', 'WHEAT_SOWINGDATE_TIDY',
    'ANTHESIS_CAT', 'CRIT_PERIOD_FISCHER_CAT', 'SPIKE_GROWTH_PERIOD_CAT',
    'CRIT_PERIOD_BEFORE_CRIT_PERIOD_CAT',
    'CRIT_PERIOD_AFTER_CRIT_PERIOD_CAT',
    'CRIT_PERIOD_GRAIN_FILL_PERIOD_CAT'
])

# Set once per worker process by _init_worker (avoids re-pickling the
# schema with every task).
_SCHEMA = None
_SCHEMA_NAMES = None


class CastError(Exception):
    """Raised by process_file when one or more columns can't be cast.
    bad_cols is a list of (column, file_type, target_type, arrow_message)."""
    def __init__(self, bad_cols):
        super().__init__(bad_cols)
        self.bad_cols = bad_cols

    def __str__(self):
        return "; ".join(f"{c}: {src} -> {dst}" for c, src, dst, _ in self.bad_cols)


def _skip_col(name):
    return name in DROP_COLS or name.startswith("__index_level_")


def _read_schema_with_retry(path, attempts=READ_ATTEMPTS):
    for i in range(attempts):
        try:
            return pq.read_schema(path)
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def build_unified_schema(sample_files, n_threads=16):
    """
    Read schemas (metadata only) from a sample of files and build one schema
    for the whole output. Strings and date/time columns keep their type;
    every other non-excluded column becomes float64.
    """
    # Footer reads are pure I/O wait, so read them in parallel
    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        schemas = list(ex.map(_read_schema_with_retry, sample_files))

    col_types = {}  # col_name -> pyarrow type
    for schema in schemas:
        for name, dtype in zip(schema.names, schema.types):
            if _skip_col(name):
                continue
            if pa.types.is_dictionary(dtype):  # pandas categoricals
                dtype = dtype.value_type
            prev = col_types.get(name)
            if prev is None or pa.types.is_null(prev):
                col_types[name] = dtype
            elif pa.types.is_null(dtype):
                continue
            elif pa.types.is_temporal(dtype) or pa.types.is_temporal(prev):
                # Never let a date column be promoted to float.
                if not pa.types.is_temporal(prev):
                    col_types[name] = dtype
            elif pa.types.is_floating(dtype) or pa.types.is_floating(prev):
                col_types[name] = pa.float64()

    final_types = {}
    for name, dtype in col_types.items():
        if pa.types.is_timestamp(dtype):
            # Standardise the unit so files written with us/ns agree.
            final_types[name] = pa.timestamp('ns', tz=dtype.tz)
        elif pa.types.is_temporal(dtype):
            final_types[name] = dtype
        elif name in EXCLUDE_COLS:
            final_types[name] = pa.string() if pa.types.is_null(dtype) else dtype
        elif pa.types.is_string(dtype) or pa.types.is_large_string(dtype):
            final_types[name] = dtype
        else:
            final_types[name] = pa.float64()

    return pa.schema([(n, final_types[n]) for n in sorted(final_types)])


def _init_worker(schema):
    global _SCHEMA, _SCHEMA_NAMES
    _SCHEMA = schema
    _SCHEMA_NAMES = set(schema.names)


def _read_with_retry(path, attempts=READ_ATTEMPTS):
    """
    Open the file and read only the columns that are in the unified schema,
    retrying on OSError (transient network filesystem glitches).
    Returns (file_cols, present_cols, table).
    """
    for i in range(attempts):
        try:
            pf = pq.ParquetFile(path)
            file_cols = pf.schema_arrow.names
            present = [c for c in file_cols if c in _SCHEMA_NAMES]
            table = pf.read(columns=present, use_threads=False)
            return file_cols, present, table
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def process_file(path):
    """
    Read only the columns we need, cast to the unified schema, and add any
    missing columns as nulls (e.g. *_SHADING columns in control files).

    Returns (table, extra_cols, n_missing). Raises CastError listing every
    column that could not be cast.
    """
    file_cols, present, table = _read_with_retry(path)
    extras = [c for c in file_cols if c not in _SCHEMA_NAMES and not _skip_col(c)]

    n_rows = table.num_rows
    cols = {name: table.column(name) for name in present}

    arrays, bad = [], []
    for field in _SCHEMA:
        col = cols.get(field.name)
        if col is None:
            col = pa.chunked_array([pa.nulls(n_rows, type=field.type)])
        elif col.type != field.type:
            try:
                col = col.cast(field.type)
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError, pa.ArrowTypeError) as e:
                bad.append((field.name, str(col.type), str(field.type),
                            str(e).splitlines()[0]))
                continue
        arrays.append(col)

    if bad:
        raise CastError(bad)

    out = pa.Table.from_arrays(arrays, schema=_SCHEMA)
    return out, extras, len(_SCHEMA) - len(present)


def _print_cast_problems(cast_problems, n_files_total):
    print(f"\nCAST PROBLEMS: {len(cast_problems)} column/type combination(s) could not be "
          f"cast to the unified schema:")
    print(f"  {'column':<50} {'type in file':<20} {'schema type':<15} files")
    for (col, src, dst), n in sorted(cast_problems.items(), key=lambda kv: -kv[1]):
        print(f"  {col:<50} {src:<20} {dst:<15} {n}/{n_files_total}")
    print("  -> Fix: adjust build_unified_schema (or EXCLUDE_COLS) for these columns.")


def combine_processed_files(db_dir, insite, output_path, filters=None, n_workers=8):
    all_files = sorted(
        os.path.join(db_dir, f)
        for f in os.listdir(db_dir)
        if (
            f.endswith(".parquet")
            and insite.lower() in f.lower()
            # and "full" in f.lower()
            and "all" not in f.lower()
            and (not filters or all(flt in f for flt in filters))
        )
    )

    print(f"Found {len(all_files)} files to process")
    if not all_files:
        print("No matching files found.")
        return

    # Sample evenly across the sorted file list (spans years, treatments
    # and cultivars) to catch column and type variations
    n_sample = min(N_SCHEMA_SAMPLE, len(all_files))
    sample_files = [all_files[int(i * len(all_files) / n_sample)] for i in range(n_sample)]

    t = time.time()
    print(f"Reading schemas from {n_sample} sample files to unify types...")
    unified_schema = build_unified_schema(sample_files)
    n_temporal = sum(pa.types.is_temporal(f.type) for f in unified_schema)
    print(f"Unified schema built with {len(unified_schema)} columns "
          f"({n_temporal} date/time columns kept as dates; dropped: {sorted(DROP_COLS)}) "
          f"in {time.time() - t:.1f}s")

    # Pre-flight: test the schema on one file in this process so type
    # problems are reported immediately instead of after thousands of failures.
    _init_worker(unified_schema)
    try:
        process_file(all_files[0])
    except CastError as e:
        _print_cast_problems(Counter({(c, s, d): 1 for c, s, d, _ in e.bad_cols}), 1)
        raise SystemExit("Aborting: unified schema does not fit the first file.")
    print("Pre-flight check passed on first file.")

    writer = pq.ParquetWriter(
        output_path,
        unified_schema,
        compression="zstd",
        use_dictionary=True,
    )

    files_processed = 0
    flushes = 0
    total_rows = 0
    files_with_missing_cols = 0
    failed_files = []
    extra_col_counts = Counter()
    cast_problems = Counter()  # (column, file_type, schema_type) -> n files
    buffer, buffered_rows = [], 0
    t = time.time()

    def flush():
        """Concatenate buffered tables and write them as one large row group."""
        nonlocal buffer, buffered_rows, flushes, total_rows
        if not buffer:
            return
        big_table = pa.concat_tables(buffer)
        writer.write_table(big_table)
        flushes += 1
        total_rows += big_table.num_rows
        del big_table
        buffer, buffered_rows = [], 0

    try:
        with ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_init_worker,
            initargs=(unified_schema,),
        ) as executor:
            futures = {executor.submit(process_file, f): f for f in all_files}
            for future in as_completed(futures):
                path = futures.pop(future)  # release the result once handled
                try:
                    table, extras, n_missing = future.result()
                except CastError as e:
                    for c, s, d, _ in e.bad_cols:
                        cast_problems[(c, s, d)] += 1
                    failed_files.append(path)
                    if len(failed_files) <= 3:  # don't spam the log
                        print(f"CAST ERROR in {os.path.basename(path)}: {e}")
                except Exception as e:
                    print(f"ERROR processing {path}: {e}")
                    failed_files.append(path)
                else:
                    if n_missing:
                        files_with_missing_cols += 1
                    extra_col_counts.update(extras)

                    buffer.append(table)
                    buffered_rows += table.num_rows
                    files_processed += 1

                    if buffered_rows >= ROW_GROUP_ROWS:
                        flush()

                    if files_processed % 1000 == 0:
                        rate = files_processed / (time.time() - t)
                        left = (len(all_files) - files_processed) / rate / 60
                        print(f"  {files_processed}/{len(all_files)} files processed "
                              f"({rate:.0f} files/s, ~{left:.1f} min left)", flush=True)
                    continue

                # Fail fast: many failures and not one success = systematic problem.
                if len(failed_files) >= FAIL_FAST_AFTER and files_processed == 0:
                    if cast_problems:
                        _print_cast_problems(cast_problems, len(failed_files))
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise RuntimeError(
                        f"First {len(failed_files)} files all failed - aborting. "
                        f"See errors above.")

        flush()  # write whatever is left in the buffer
    finally:
        writer.close()

    print(f"\nFinished writing {files_processed} of {len(all_files)} files "
          f"({total_rows:,} rows, {flushes} flushes) to {output_path}")
    print(f"Files that had missing columns filled with nulls: {files_with_missing_cols}")

    if extra_col_counts:
        print(f"\nWARNING: {len(extra_col_counts)} columns were found in some files but are "
              f"NOT in the unified schema, so they were NOT written:")
        for col, n in extra_col_counts.most_common(20):
            print(f"  {col}: present in {n} files")

    if cast_problems:
        _print_cast_problems(cast_problems, len(all_files))

    if failed_files:
        print(f"\nWARNING: {len(failed_files)} files failed and were NOT included "
              f"(first 20 shown):")
        for p in failed_files[:20]:
            print("  ", p)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <insite> [filter1 filter2 ...]")
        sys.exit(1)

    insite = sys.argv[1]
    filters = sys.argv[2:] or None
    if filters:
        print(f"Applying additional filters: {filters}")

    out_dir = cfg.PROCESSED_DATA_FILES_DIR
    os.makedirs(out_dir, exist_ok=True)

    # Filters go into the output name so runs with different filters
    # (e.g. one per year) don't overwrite each other
    suffix = "_" + "_".join(f.strip("_") for f in filters) if filters else ""
    output_path = os.path.join(
        out_dir, f"{insite}{suffix}_dryland_shading_experiment_all_processed_results.parquet")

    combine_processed_files(cfg.DRYLAND_PROCESSED_FILES_BEFORE_BINDING_DIR, insite,
                            output_path, filters,
                            n_workers=int(os.environ.get("SLURM_CPUS_PER_TASK", 8)))

    print(f"\nTotal runtime: {time.time() - start_time:.2f}s")
    print("Ended:", datetime.datetime.now())