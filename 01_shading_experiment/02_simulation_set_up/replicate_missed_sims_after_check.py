"""
Replicate an APSIM template for every year / shift / DOY / cultivar.

Usage:
    python3 02_replicate_shaded_sims.py <site>
        Full run. Creates any expected file that does not exist yet.
        Existing files are NEVER overwritten (they may have been edited).

    python3 02_replicate_shaded_sims.py <site> --list problem_files_<site>.txt
        Only (re)creates the files named in the list written by
        check_replicated_sims.py. Listed files are overwritten with a fresh
        copy of the template, including NO_FCO2 files that already exist.
"""
import os
import sys
import time
import shutil
import tempfile
import datetime
from pathlib import Path

import psutil

# =============================================================================
# Settings
# =============================================================================
REQUIRED_STRING = "[Wheat].Leaf.Photosynthesis.FCO2"   # must be present in every file

YEAR_RANGE = range(1995, 2025)
SHIFTS = ["shading"]
DOY_RANGE = range(128, 366)
CULTIVARS = ["SpringVQQ", "SpringQ", "SpringQM", "SpringM", "SpringMS", "SpringS",
             "SpringSVS", "SpringVS", "WinterVQ", "WinterQ", "WinterM", "WinterVS"]

MAX_RETRIES = 5                  # attempts per file before recording it as failed
RETRY_WAIT_S = 10                # wait grows: 10s, 20s, 30s, ...
MAX_CONSECUTIVE_FAILURES = 20    # abort if the filesystem looks down; a rerun resumes
PROGRESS_EVERY = 1000

# =============================================================================
# Metadata
# =============================================================================
try:
    print("The script used to generate this output is", os.path.basename(__file__))
    print("The script above can be found in this directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode; __file__ is not defined.")

print("This script started running at:", datetime.datetime.now())
start_time = time.time()


def print_usage(stage):
    process = psutil.Process(os.getpid())
    mem_MB = process.memory_info().rss / 1024 ** 2
    print(f"{stage} - Memory usage: {mem_MB:.2f} MB", flush=True)


print_usage("Start")

# =============================================================================
# Configuration and arguments
# =============================================================================
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg  # noqa: E402

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    print(__doc__)
    sys.exit(2)

insite = args[0]
LIST_FILE = None
if "--list" in args:
    i = args.index("--list")
    if i + 1 >= len(args):
        print("Error: --list needs a file path.")
        sys.exit(2)
    LIST_FILE = args[i + 1]

TEMPLATE_DIR = cfg.SHADING_APSIMX_TEMPLATES_FOR_DUPLICATION_DIR
SOURCE_FILE_PATH = os.path.join(
    TEMPLATE_DIR,
    f"{insite}_2024_radiation_shading_67_128_SpringVQQ.apsimx"
)
OUTPUT_DIRECTORY = cfg.SHADING_APSIM_SIMULATIONS_DIR


# =============================================================================
# Helpers
# =============================================================================
def copy_with_retry(src, dst, ref_size):
    """Copy via a temporary name, check the size, then rename into place.
    Returns None on success or the last error message on failure."""
    tmp = dst + ".tmp"
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            shutil.copy2(src, tmp)
            size = os.path.getsize(tmp)
            if size != ref_size:
                raise OSError(f"size mismatch after copy ({size} vs {ref_size} bytes)")
            os.replace(tmp, dst)   # atomic: dst is never left half-written
            return None
        except OSError as e:
            last_error = f"{type(e).__name__}: {e}"
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < MAX_RETRIES:
                print(f"  Retry {attempt}/{MAX_RETRIES - 1} for {os.path.basename(dst)}: {last_error}",
                      flush=True)
                time.sleep(RETRY_WAIT_S * attempt)
    return last_error


def names_from_grid(site, variable, percentchange):
    return [f"{site}_{year}_{variable}_{shift}_{percentchange}_{doy:03d}_{cv}.apsimx"
            for year in YEAR_RANGE for shift in SHIFTS
            for doy in DOY_RANGE for cv in CULTIVARS]


def names_from_list(list_file, site):
    """Read file names from a problem list (STATUS<tab>NAME<tab>DETAIL, or one name per line)."""
    names, seen = [], set()
    with open(list_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            name = parts[1] if len(parts) >= 2 else parts[0]
            name = os.path.basename(name.strip())
            if not (name.startswith(f"{site}_") and name.endswith(".apsimx")):
                print(f"  Skipping list entry not for site '{site}': {name}")
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


# =============================================================================
# Main
# =============================================================================
def replicate_apsim_files(source_file, output_directory, list_file=None):
    """Returns 0 if every target file is in place, 1 otherwise."""

    # --- Check the template ---------------------------------------------------
    if not os.path.isfile(source_file):
        print(f"Error: source file '{source_file}' not found.")
        return 1

    base_name = os.path.basename(source_file)
    name_parts = base_name.replace(".apsimx", "").split("_")
    if len(name_parts) != 7:
        print("Error: filename doesn't match 'site_year_variable_shift_percentchange_doy_cultivar.apsimx'")
        print(f"Found {len(name_parts)} parts: {name_parts}")
        return 1

    site, template_year, variable, shift, percentchange, original_doy, cultivar = name_parts
    print(f"Processing file: {base_name}")
    print(f"Parsed components: site={site}, year={template_year}, variable={variable}, shift={shift}, "
          f"percentchange={percentchange}, doy={original_doy}, cultivar={cultivar}")

    # --- Decide which files to make -------------------------------------------
    if list_file:
        if not os.path.isfile(list_file):
            print(f"Error: list file '{list_file}' not found.")
            return 1
        targets = names_from_list(list_file, site)
        overwrite = True
        print(f"Mode: LIST - {len(targets)} files from {list_file} (listed files are overwritten)")
    else:
        targets = names_from_grid(site, variable, percentchange)
        overwrite = False
        print(f"Mode: FULL - {len(targets)} expected files (existing files are left untouched)")

    if not targets:
        print("Nothing to do.")
        return 0

    os.makedirs(output_directory, exist_ok=True)

    # --- Work from a local copy so shared-storage glitches on the template can't break the run
    tmpdir = tempfile.mkdtemp(prefix=f"rep_{site}_", dir=os.environ.get("TMPDIR"))
    try:
        local_template = os.path.join(tmpdir, base_name)
        shutil.copy2(source_file, local_template)

        with open(local_template, "rb") as f:
            data = f.read()
        if len(data) != os.path.getsize(source_file):
            print("Error: local copy of the template is incomplete.")
            return 1
        if REQUIRED_STRING.encode() not in data:
            print(f"Error: template does not contain '{REQUIRED_STRING}'. "
                  f"Fix the template before replicating: {source_file}")
            return 1
        ref_size = len(data)
        del data
        print(f"Template OK: {ref_size} bytes, contains '{REQUIRED_STRING}'")
        print(f"Working from local copy: {local_template}", flush=True)

        # --- Replicate ---------------------------------------------------------
        created = skipped = 0
        consecutive_failures = 0
        failed = []
        created_names = []
        aborted = False

        for processed, new_filename in enumerate(targets, 1):
            new_filepath = os.path.join(output_directory, new_filename)

            if not overwrite and os.path.exists(new_filepath):
                skipped += 1
            else:
                err = copy_with_retry(local_template, new_filepath, ref_size)
                if err is None:
                    created += 1
                    created_names.append(new_filename)
                    consecutive_failures = 0
                else:
                    failed.append((new_filename, err))
                    consecutive_failures += 1
                    print(f"Error creating file {new_filename}: {err}", flush=True)
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(f"\nAborting: {consecutive_failures} consecutive failures. "
                              f"The output filesystem may be unavailable. Rerun this script.")
                        aborted = True
                        break

            if processed % PROGRESS_EVERY == 0:
                print(f"Processed {processed}/{len(targets)} "
                      f"(created {created}, already existed {skipped}, failed {len(failed)})",
                      flush=True)

        # --- Output lists --------------------------------------------------------
        created_list_path = os.path.join(os.getcwd(), f"created_files_{site}.txt")
        if created_names:
            with open(created_list_path, "w") as f:
                f.write("\n".join(created_names) + "\n")

        failed_list_path = os.path.join(os.getcwd(), f"failed_files_{site}.txt")
        if failed:
            with open(failed_list_path, "w") as f:
                for name, err in failed:
                    f.write(f"{name}\t{err}\n")
        elif os.path.exists(failed_list_path):
            os.remove(failed_list_path)   # clear a stale list from an earlier run

        # --- Summary (printed once) ----------------------------------------------
        print("\nSummary:")
        print(f"- Site: {site}")
        print(f"- Mode: {'LIST (' + list_file + ')' if list_file else 'FULL'}")
        print(f"- Target files: {len(targets)}")
        print(f"- Created this run: {created}")
        print(f"- Already existed (left untouched): {skipped}")
        print(f"- Failed: {len(failed)}")
        print(f"- Files saved in: {output_directory}")
        if created_names:
            print(f"- Newly created file list (these still need your edit step): {created_list_path}")
        if failed:
            print(f"- Failed file list: {failed_list_path}")

        ok = (not aborted) and (not failed) and (created + skipped == len(targets))
        print("\nRESULT:", "SUCCESS" if ok else "INCOMPLETE - rerun this script")
        return 0 if ok else 1

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    exit_code = replicate_apsim_files(SOURCE_FILE_PATH, OUTPUT_DIRECTORY, LIST_FILE)

    print_usage("End")
    elapsed = time.time() - start_time
    print(f"Total runtime: {elapsed:.2f} seconds")
    print("This script ended running at:", datetime.datetime.now())

    sys.exit(exit_code)   # non-zero makes Slurm mark the job FAILED