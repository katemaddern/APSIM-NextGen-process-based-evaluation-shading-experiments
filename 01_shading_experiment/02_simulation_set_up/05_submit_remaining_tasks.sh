#!/bin/bash -l
# =============================================================================
# Submit ONLY the APSIM array tasks that have not finished yet.
#
# A task counts as finished if it has a row in any summary_<jobid>.csv in the
# timing log directory (a row is written only when a task reaches the end).
# Tasks that are currently running or pending in Slurm are also skipped.
#
# Usage (login node is fine - the manifest already exists, nothing heavy runs):
#   bash 05_submit_remaining_tasks.sh                 # use all summary_*.csv
#   bash 05_submit_remaining_tasks.sh 1020329         # only this job's summary
#   DRY_RUN=1 bash 05_submit_remaining_tasks.sh       # show, don't submit
#
# IMPORTANT: task N always means manifest lines N*FILES_PER_TASK ... so the
# manifest and FILES_PER_TASK must be exactly the same as in the original run.
# =============================================================================

set -euo pipefail

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SCRIPT_DIR="$SIMSETUP_SCRIPTS_DIR"
MANIFEST="$SHADING_APSIM_MANIFEST"
files_per_task="$FILES_PER_TASK"
throttle="${THROTTLE:-$ARRAY_THROTTLE_DEFAULT}"

TIMING_DIR="$SIMSETUP_SCRIPTS_DIR/logs/05_apsim_sims_timing_logs"
LOG_DIR="$SCRIPT_DIR/logs/05_run_apsim_sims"
ARRAY_SCRIPT="$SCRIPT_DIR/05_run_apsim_array.sh"
DRY_RUN="${DRY_RUN:-0}"

[[ -f "$MANIFEST" ]]     || { echo "ERROR: manifest not found: $MANIFEST" >&2; exit 1; }
[[ -f "$ARRAY_SCRIPT" ]] || { echo "ERROR: array script not found: $ARRAY_SCRIPT" >&2; exit 1; }
mkdir -p "$LOG_DIR"

# -----------------------------------------------------------------------------
# Total number of tasks (same formula as the controller)
# -----------------------------------------------------------------------------
total_files=$(wc -l < "$MANIFEST")
num_tasks=$(( (total_files + files_per_task - 1) / files_per_task ))

# -----------------------------------------------------------------------------
# Finished tasks: column 2 of the summary file(s)
# -----------------------------------------------------------------------------
if (( $# > 0 )); then
    summaries=()
    for jid in "$@"; do summaries+=("$TIMING_DIR/summary_${jid}.csv"); done
else
    shopt -s nullglob
    summaries=("$TIMING_DIR"/summary_*.csv)
    shopt -u nullglob
fi

done_ids=""
if (( ${#summaries[@]} > 0 )); then
    done_ids=$(awk -F, 'FNR > 1 && $2 ~ /^[0-9]+$/ { print $2 }' "${summaries[@]}" | sort -u)
fi

# -----------------------------------------------------------------------------
# Tasks still running/pending in Slurm (so we never start a duplicate)
# -----------------------------------------------------------------------------
active_ids=$(squeue -h -r -u "$USER" -n APX_array -o "%i" 2>/dev/null \
    | awk -F_ 'NF == 2 && $2 ~ /^[0-9]+$/ { print $2 }' | sort -u)

# -----------------------------------------------------------------------------
# Remaining = all task ids - finished - active
# -----------------------------------------------------------------------------
remaining=$(
    comm -23 \
        <(seq 0 $((num_tasks - 1)) | sort -u) \
        <(printf '%s\n%s\n' "$done_ids" "$active_ids" | grep -v '^$' | sort -u) \
    | sort -n
)

n_done=$(grep -c . <<< "$done_ids" || true)
n_active=$(grep -c . <<< "$active_ids" || true)
n_remaining=$(grep -c . <<< "$remaining" || true)

echo "============================================================"
echo "Manifest:          $MANIFEST ($total_files files)"
echo "Files per task:    $files_per_task"
echo "Total tasks:       $num_tasks (0-$((num_tasks - 1)))"
echo "Summary files:     ${summaries[*]:-none}"
echo "Finished tasks:    $n_done"
echo "Running/pending:   $n_active"
echo "Still to run:      $n_remaining"
echo "============================================================"

if (( n_remaining == 0 )); then
    echo "Nothing to submit."
    exit 0
fi

# Compress ids into Slurm ranges, e.g. 137-139,149-200
array_spec=$(awk '
    NR == 1        { s = p = $1; next }
    $1 == p + 1    { p = $1; next }
                   { out = out (out ? "," : "") (s == p ? s : s "-" p); s = p = $1 }
    END            { out = out (out ? "," : "") (s == p ? s : s "-" p); print out }
' <<< "$remaining")

echo "Array spec: ${array_spec}%${throttle}"

cmd=(sbatch
     --array="${array_spec}%${throttle}"
     -e "$LOG_DIR/array_%A_%a_error.txt"
     -o "$LOG_DIR/array_%A_%a_output.txt"
     "$ARRAY_SCRIPT")

if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY RUN - would run:"
    printf ' %q' "${cmd[@]}"; echo
else
    "${cmd[@]}"
fi