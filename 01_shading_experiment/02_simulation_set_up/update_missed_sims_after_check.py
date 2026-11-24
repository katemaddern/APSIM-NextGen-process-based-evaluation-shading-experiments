import os
import sys
import re
import json
import time
import datetime
import psutil
from pathlib import Path

# --- Metadata ---
try:
    print("The script used to generate this output is", os.path.basename(__file__))
    print("The script above can be found in this directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode; __file__ is not defined.")

print("This script started running at:", datetime.datetime.now())

# --- Timing ---
start_time = time.time()

# --- Memory Usage ---
def print_usage(stage):
    process = psutil.Process(os.getpid())
    mem_MB = process.memory_info().rss / 1024 ** 2
    print(f"{stage} - Memory usage: {mem_MB:.2f} MB")

print_usage("Start")

# Load configuration
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg
print("Config loaded from:", cfg._config_path)

MET_FILE_LOCATION = cfg.SHADING_MET_OUT_DIR
print("MET_OUT_DIR:", MET_FILE_LOCATION)

# Directory containing the .apsimx files
directory = cfg.SHADING_APSIM_SIMULATIONS_DIR

# Pattern: site_year_variable_shift_percentchange_doy_cultivar.apsimx
PATTERN = re.compile(r'^([^_]+)_(\d{4})_([^_]+)_([^_]+)_([^_]+)_([^_]+)_([^_]+)\.apsimx$')

# Filename cultivar code -> APSIM cultivar name used in the sowing rule
CULTIVAR_MAPPING = {
    "SpringVQQ": "Spring Very Quick-Quick",
    "SpringQ": "Spring Quick",
    "SpringQM": "Spring Quick-Mid",
    "SpringM": "Spring Mid",
    "SpringMS": "Spring Mid-Slow",
    "SpringS": "Spring Slow",
    "SpringSVS": "Spring Slow-Very Slow",
    "SpringVS": "Spring Very Slow",
    "WinterVQ": "Winter Very-Quick",
    "WinterQ": "Winter Quick",
    "WinterM": "Winter Mid",
    "WinterVS": "Winter Very Slow",
    "Scepter": "Scepter",
}

# ------------------------------------------------------------
# Which files does this run process?
#   - --list <file>                         -> the file names in that list
#       (problem_files_<site>.txt from check_replicated_sims.py, or
#        created_files_<site>.txt / any file with one name per line)
#   - Filenames given on the command line  -> just those (for testing by hand)
#   - Otherwise, running as a SLURM array task -> this task's slice of
#     TASK_MANIFEST (FILES_PER_TASK files per task, set in config.sh)
# ------------------------------------------------------------
def read_list_file(list_file):
    """Read .apsimx names from a list file. Accepts STATUS<tab>NAME<tab>DETAIL lines
    (problem_files_<site>.txt) or one file name per line. Duplicates are removed."""
    names, seen = [], set()
    with open(list_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            name = parts[1] if len(parts) >= 2 else parts[0]
            name = os.path.basename(name.strip())
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def get_files_to_process():
    args = sys.argv[1:]

    if "--list" in args:
        i = args.index("--list")
        if i + 1 >= len(args):
            print("Error: --list needs a file path.")
            sys.exit(1)
        list_file = args[i + 1]
        if not os.path.isfile(list_file):
            print(f"Error: list file not found: {list_file}")
            sys.exit(1)
        files = read_list_file(list_file)
        print(f"List mode: {len(files)} files from {list_file}")
        return files

    if args:
        return args

    manifest = os.environ.get("TASK_MANIFEST")
    task_id = os.environ.get("SLURM_ARRAY_TASK_ID")
    if manifest is None or task_id is None:
        print("Error: give .apsimx filename(s) as arguments, use --list <file>, or run as an "
              "array job with TASK_MANIFEST set (use the submit script).")
        sys.exit(1)

    task_id = int(task_id)
    start = task_id * cfg.FILES_PER_TASK
    end = start + cfg.FILES_PER_TASK

    with open(manifest) as f:
        all_files = [line.strip() for line in f if line.strip()]

    print(f"Array task {task_id}: manifest entries {start} to {min(end, len(all_files)) - 1} "
          f"(of {len(all_files)} total)")
    return all_files[start:end]


# Recursively update:
#   - Weather FileName (.met path)
#   - Clock Start/End
#   - CultivarName parameter in any Manager script (the sowing rule)
def update_json_data(obj, met_path, year, cultivar_name, counts):
    if isinstance(obj, dict):
        obj_type = obj.get("$type")

        # Clock dates
        if obj_type == "Models.Clock, Models" and "Start" in obj and "End" in obj:
            end_year = int(year) + 1
            obj["Start"] = f"{year}-01-01T00:00:00"
            obj["End"] = f"{end_year}-02-28T00:00:00"
            counts["clock"] += 1
            print(f"  Updated Clock Start/End to: {year}-01-01 / {end_year}-02-28")

        # Cultivar in the sowing rule (Manager "Parameters" list of Key/Value pairs)
        if obj_type == "Models.Manager, Models":
            for param in obj.get("Parameters") or []:
                if isinstance(param, dict) and param.get("Key") == "CultivarName":
                    old = param.get("Value")
                    param["Value"] = cultivar_name
                    counts["cultivar"] += 1
                    print(f"  Updated CultivarName in '{obj.get('Name')}': {old} -> {cultivar_name}")

        for key, value in obj.items():
            if key == "FileName" and isinstance(value, str) and value.endswith(".met"):
                obj[key] = met_path
                counts["met"] += 1
                print(f"  Updated FileName to: {met_path}")
            elif isinstance(value, (dict, list)):
                update_json_data(value, met_path, year, cultivar_name, counts)

    elif isinstance(obj, list):
        for item in obj:
            update_json_data(item, met_path, year, cultivar_name, counts)


# Process one .apsimx file. Returns True on success, False on failure.
def process_file(filename):
    if not filename.endswith('.apsimx'):
        filename = filename + '.apsimx'

    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath):
        print(f"Error: file {filepath} does not exist!")
        return False

    match = PATTERN.search(filename)
    if not match:
        print(f"Error: filename doesn't match 'site_year_variable_shift_percentchange_doy_cultivar.apsimx': {filename}")
        return False

    site, year, variable, shift, percentchange, doy, cultivar = match.groups()
    print(f"Processing {filename} - site: {site}, year: {year}, variable: {variable}, "
          f"shift: {shift}, percentchange: {percentchange}, doy: {doy}, cultivar: {cultivar}")

    # Cultivar code from filename -> full APSIM cultivar name
    cultivar_name = CULTIVAR_MAPPING.get(cultivar)
    if cultivar_name is None:
        print(f"Error: cultivar code '{cultivar}' not in CULTIVAR_MAPPING "
              f"(known: {', '.join(CULTIVAR_MAPPING)})")
        return False

    # Met file name does NOT include the cultivar
    met_path = f"{MET_FILE_LOCATION}/{site}_{year}_{variable}_{shift}_{percentchange}_{doy}.met"
    if not os.path.isfile(met_path):
        print(f"Error: met file does not exist: {met_path}")
        return False

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON in {filename}: {e}")
        return False

    counts = {"met": 0, "clock": 0, "cultivar": 0}
    update_json_data(data, met_path, year, cultivar_name, counts)

    if counts["met"] == 0 or counts["clock"] == 0 or counts["cultivar"] == 0:
        print(f"Error: nothing updated in {filename} (met: {counts['met']}, clock: {counts['clock']}, "
              f"cultivar: {counts['cultivar']}) - file not written")
        return False

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Successfully updated {filename}")
    return True


# --- Main ---
files = get_files_to_process()
failed = []

for fn in files:
    print("------------------------------------------------------------")
    if not process_file(fn):
        failed.append(fn)

print("============================================================")
print(f"Done: {len(files) - len(failed)} succeeded, {len(failed)} failed")
if failed:
    print("Failed files:")
    for fn in failed:
        print(f"  {fn}")

# --- Final usage and timing ---
print_usage("End")
elapsed = time.time() - start_time
print(f"Total runtime: {elapsed:.2f} seconds")
print("This script ended running at:", datetime.datetime.now())

sys.exit(1 if failed else 0)