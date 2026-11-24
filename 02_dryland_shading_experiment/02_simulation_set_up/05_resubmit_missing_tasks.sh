#!/bin/bash -l
# =============================================================================
# Rerun ONLY the APSIM simulations named in a list file.
#
# Usage:
#   ./05_resubmit_missing_tasks.sh [<name_list>]
#
#   <name_list>  Default: $LIST_DEFAULT (below). Quoted names ('name' or
#                "name", with or without a [site] header) or one per line.
#
# Options (environment variables):
#   DRY_RUN=1     Check the names and show what would be submitted.
#   THROTTLE=N    Max concurrent tasks (default: ARRAY_THROTTLE_DEFAULT).
#   PER_TASK=N    Files per array task for this job only (default: 10).
#                 Does NOT change FILES_PER_TASK in config.sh.
#
# The list is passed to 05_run_apsim_array.sh as APSIM_FILE_LIST, which
# then uses it instead of the manifest: task N runs list entries
# N*FILES_PER_TASK ... so exactly the listed files are run.
# Do not edit the list file while the job is queued or running.
# =============================================================================

set -euo pipefail

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LIST_DEFAULT="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/01_shading_experiment/02_simulation_set_up/waikerie_missing_db_files.txt"

NAME_LIST=$(readlink -f "${1:-$LIST_DEFAULT}")

SCRIPT_DIR="$DRYLAND_SIMSETUP_SCRIPTS_DIR"
SIM_DIR="$DRYLAND_APSIM_SIMULATIONS_DIR"
MANIFEST="$DRYLAND_APSIM_MANIFEST"
ARRAY_SCRIPT="$SCRIPT_DIR/05_run_apsim_array.sh"
TIMING_DIR="$SCRIPT_DIR/logs/05_apsim_sims_timing_logs"
LOG_DIR="$SCRIPT_DIR/logs/05_run_apsim_sims"

files_per_task="${PER_TASK:-100}"
throttle="${THROTTLE:-$ARRAY_THROTTLE_DEFAULT}"
dry_run="${DRY_RUN:-0}"

# Must stay identical to the copy in 05_run_apsim_array.sh.
read_name_list() {
    local f="$1"
    if grep -qE "['\"]" "$f"; then
        grep -oE "'[^']+'|\"[^\"]+\"" "$f" | tr -d "'\""
    else
        tr -d '\r' < "$f" | sed -E 's/[[:space:],]+//g' | grep -vE '^$|^\[.*\]$'
    fi | awk '!seen[$0]++'
}

# -----------------------------------------------------------------------------
# Checks
# -----------------------------------------------------------------------------

for f in "$NAME_LIST" "$ARRAY_SCRIPT"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: Not found: $f" >&2
        exit 1
    fi
done

if ! grep -q 'APSIM_FILE_LIST' "$ARRAY_SCRIPT"; then
    echo "ERROR: $ARRAY_SCRIPT does not support APSIM_FILE_LIST." >&2
    echo "Install the updated 05_run_apsim_array.sh first." >&2
    exit 1
fi

if ! [[ "$files_per_task" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: PER_TASK must be a positive integer. Got: $files_per_task" >&2
    exit 1
fi

if ! grep -q 'APSIM_FILES_PER_TASK' "$ARRAY_SCRIPT"; then
    echo "ERROR: $ARRAY_SCRIPT does not support APSIM_FILES_PER_TASK." >&2
    echo "Install the updated 05_run_apsim_array.sh first." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"

mapfile -t names < <(read_name_list "$NAME_LIST")
n_names=${#names[@]}

if (( n_names == 0 )); then
    echo "ERROR: No simulation names found in $NAME_LIST" >&2
    exit 1
fi

# -----------------------------------------------------------------------------
# Check every name resolves to a file (same rules as the array script)
# -----------------------------------------------------------------------------

unresolved=()
for entry in "${names[@]}"; do
    [[ "$entry" == /* && -f "$entry" ]] && continue
    name="${entry##*/}"; name="${name%.apsimx}"
    [[ -f "$SIM_DIR/$name.apsimx" ]] || unresolved+=("$name")
done

not_found=()
if (( ${#unresolved[@]} > 0 )) && [[ -f "$MANIFEST" ]]; then
    # One pass over the manifest for anything not directly in SIM_DIR.
    mapfile -t not_found < <(
        printf '%s\n' "${unresolved[@]}" | awk '
            NR == FNR { want[$0] = 1; next }
            { b = $0; sub(/.*\//, "", b); sub(/\.apsimx$/, "", b); if (b in want) delete want[b] }
            END { for (n in want) print n }' - "$MANIFEST"
    )
else
    not_found=("${unresolved[@]}")
fi

num_tasks=$(( (n_names + files_per_task - 1) / files_per_task ))
last_task=$(( num_tasks - 1 ))
array_spec="0-${last_task}%${throttle}"

echo "Name list:       $NAME_LIST"
echo "Sim dir:         $SIM_DIR"
echo "Files to run:    $n_names"
echo "Files per task:  $files_per_task"
echo "Tasks:           $num_tasks"
echo "Array spec:      $array_spec"

if (( ${#not_found[@]} > 0 )); then
    echo "WARNING: ${#not_found[@]} name(s) have no .apsimx file (will be logged as ERROR):" >&2
    printf '  %s\n' "${not_found[@]}" >&2
else
    echo "All $n_names names found."
fi

if [[ "$dry_run" == "1" ]]; then
    echo "DRY_RUN=1: not submitting."
    exit 0
fi

# -----------------------------------------------------------------------------
# Submit
# -----------------------------------------------------------------------------

submit_output=$(
    sbatch \
        --array="$array_spec" \
        --export=ALL,APSIM_FILE_LIST="$NAME_LIST",APSIM_FILES_PER_TASK="$files_per_task" \
        -e "$LOG_DIR/array_%A_%a_error.txt" \
        -o "$LOG_DIR/array_%A_%a_output.txt" \
        "$ARRAY_SCRIPT"
)

echo "$submit_output"

if [[ $submit_output =~ Submitted\ batch\ job\ ([0-9]+) ]]; then
    new_id="${BASH_REMATCH[1]}"
    echo "============================================================"
    echo "Submitted $n_names files as array job $new_id ($num_tasks tasks)"
    echo "Summary will be written to: $TIMING_DIR/summary_${new_id}.csv"
    echo "============================================================"
else
    echo "ERROR: Could not parse job ID from sbatch output." >&2
    exit 1
fi