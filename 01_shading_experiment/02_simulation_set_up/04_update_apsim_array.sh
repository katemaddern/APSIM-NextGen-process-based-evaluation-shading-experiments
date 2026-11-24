#!/bin/bash -l
#SBATCH --partition=Long
#SBATCH --time=12-00:00:00
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=2GB
#SBATCH --cpus-per-task=1
#SBATCH --job-name=UPDATE_array

set -uo pipefail

# =============================================================================
# Config
# =============================================================================

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SIM_DIR="$SHADING_APSIM_SIMULATIONS_DIR"
MANIFEST="$SHADING_APSIM_MANIFEST"
files_per_task="$FILES_PER_TASK"

# Resolve the real path behind the scratch symlink.
SCRATCH_REAL=$(readlink -f "$SCRATCH_BASE")

# =============================================================================
# Singularity
# =============================================================================

# Force use of the system SingularityCE installation rather than an Apptainer
# executable which may be present in a micromamba environment.
SINGULARITY="/usr/bin/singularity"

if [[ ! -x "$SINGULARITY" ]]; then
    echo "ERROR: Singularity executable not found: $SINGULARITY" >&2
    exit 1
fi

echo "Singularity: $("$SINGULARITY" --version)"

# =============================================================================
# Checks
# =============================================================================

if [[ ! -d "$SIM_DIR" ]]; then
    echo "ERROR: Simulation directory does not exist: $SIM_DIR" >&2
    exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: APSIM manifest does not exist: $MANIFEST" >&2
    echo "The manifest must be created before the array job starts." >&2
    exit 1
fi

if (( files_per_task < 1 )); then
    echo "ERROR: FILES_PER_TASK must be >= 1. Got: $files_per_task" >&2
    exit 1
fi

# =============================================================================
# SLURM variables
# =============================================================================

job_id=${SLURM_ARRAY_JOB_ID:-"local"}
task_id=${SLURM_ARRAY_TASK_ID:-0}

echo "Job ID:      $job_id"
echo "Task ID:     $task_id"
echo "Hostname:    $HOSTNAME"

# =============================================================================
# Scratch tmp
# =============================================================================

SCRATCH_TMP="${SCRATCH_BASE}/apsim_tmp_${job_id}_${task_id}"

setup_scratch_tmp() {
    echo "Setting up scratch tmp directory: $SCRATCH_TMP"

    if ! mkdir -p "$SCRATCH_TMP"; then
        echo "ERROR: Could not create scratch tmp directory: $SCRATCH_TMP" >&2
        exit 1
    fi

    echo "Scratch tmp directory created: $SCRATCH_TMP"
    df -h "$SCRATCH_TMP" || true
}

cleanup_scratch_tmp() {
    echo "Cleaning up scratch tmp directory: $SCRATCH_TMP"

    if [[ -d "$SCRATCH_TMP" ]]; then
        rm -rf "$SCRATCH_TMP"
        echo "Scratch tmp cleaned up."
    fi
}

trap cleanup_scratch_tmp EXIT

setup_scratch_tmp

export TMPDIR="${SCRATCH_TMP}"

echo "Scratch base: $SCRATCH_BASE"
echo "Scratch real: $SCRATCH_REAL"
echo "Scratch tmp:  $SCRATCH_TMP"

# =============================================================================
# Timing output
# =============================================================================

TIMING_DIR="$SIMSETUP_SCRIPTS_DIR/logs/04_update_apsim_files_timing_logs"

if ! mkdir -p "$TIMING_DIR"; then
    echo "ERROR: Could not create timing directory: $TIMING_DIR" >&2
    exit 1
fi

TIMING_FILE="${TIMING_DIR}/timing_task_${job_id}_${task_id}.csv"
SUMMARY_FILE="${TIMING_DIR}/summary_${job_id}.csv"

# =============================================================================
# Read manifest
# =============================================================================

echo "Manifest: $MANIFEST"

total_files=$(wc -l < "$MANIFEST")

echo "Total files in manifest: $total_files"

if (( total_files == 0 )); then
    echo "ERROR: Manifest is empty: $MANIFEST" >&2
    exit 1
fi

# =============================================================================
# Determine this task's file range
# =============================================================================

start_idx=$((task_id * files_per_task))
end_idx=$((start_idx + files_per_task - 1))

if (( start_idx >= total_files )); then
    echo "Array task $task_id has no work."
    echo "start_idx=$start_idx >= total_files=$total_files"
    exit 0
fi

if (( end_idx >= total_files )); then
    end_idx=$((total_files - 1))
fi

files_this_task=$((end_idx - start_idx + 1))

echo "Task $task_id processing manifest indices ${start_idx}..${end_idx}"
echo "Files assigned to this task: $files_this_task"

# Manifest is 1-based for sed, whereas task indices are zero-based.
manifest_start=$((start_idx + 1))
manifest_end=$((end_idx + 1))

mapfile -t files < <(
    sed -n "${manifest_start},${manifest_end}p" "$MANIFEST"
)

if (( ${#files[@]} != files_this_task )); then
    echo "ERROR: Expected $files_this_task files from manifest, but read ${#files[@]}" >&2
    exit 1
fi

echo "Sim dir:      $SIM_DIR"
echo "Manifest:     $MANIFEST"
echo "Timing log:   $TIMING_FILE"

# =============================================================================
# Timing init
# =============================================================================

task_start_time=$(date +%s)
task_start_human=$(date '+%Y-%m-%d %H:%M:%S')

echo "Task started at: $task_start_human"

echo "site,status,start_time,end_time,duration_seconds,exit_code" \
    > "$TIMING_FILE"

success_count=0
error_count=0
error_files=()
total_sim_time=0

# =============================================================================
# Update each apsimx file to have correct met file and clock
# =============================================================================

for filepath in "${files[@]}"; do

    filename="$(basename "$filepath")"
    insite="${filename%.parquet}"

    echo "============================================================"
    echo "Running: $insite"
    echo "File:    $filepath"
    echo "============================================================"

    if [[ ! -f "$filepath" ]]; then
        echo "ERROR: Manifest entry does not exist: $filepath" >&2

        status="ERROR"
        exit_code=2
        ((error_count++))
        error_files+=("$insite")

        sim_start_human=$(date '+%Y-%m-%d %H:%M:%S')
        sim_end_human="$sim_start_human"
        sim_duration=0

    else

        sim_start_time=$(date +%s)
        sim_start_human=$(date '+%Y-%m-%d %H:%M:%S')

        exit_code=0

        if python 04_update_met_file_location_clock_in_sim_files.py "$insite"; then
            status="SUCCESS"
            success_count=$((success_count + 1))
            echo "SUCCESS: $insite"
        else
            exit_code=$?
            status="ERROR"
            ((error_count++))
            error_files+=("$insite")

            echo "ERROR: $insite (exit code: $exit_code)"
            echo "Continuing to next file..."
        fi

        sim_end_time=$(date +%s)
        sim_end_human=$(date '+%Y-%m-%d %H:%M:%S')

        sim_duration=$((sim_end_time - sim_start_time))
    fi

    total_sim_time=$((total_sim_time + sim_duration))

    hours=$((sim_duration / 3600))
    minutes=$(((sim_duration % 3600) / 60))
    seconds=$((sim_duration % 60))

    echo "Duration: ${hours}h ${minutes}m ${seconds}s"
    echo "(${sim_duration}s, from $sim_start_human to $sim_end_human)"

    echo "${insite},${status},${sim_start_human},${sim_end_human},${sim_duration},${exit_code}" \
        >> "$TIMING_FILE"

    echo "---"

done

# =============================================================================
# Task summary
# =============================================================================

task_end_time=$(date +%s)
task_end_human=$(date '+%Y-%m-%d %H:%M:%S')
task_duration=$((task_end_time - task_start_time))

task_hours=$((task_duration / 3600))
task_minutes=$(((task_duration % 3600) / 60))
task_seconds=$((task_duration % 60))

total_processed=$((success_count + error_count))

if (( total_processed > 0 )); then
    avg_time=$((total_sim_time / total_processed))
else
    avg_time=0
fi

echo "========================================="
echo "Task $task_id completed on $HOSTNAME"
echo "Task started:       $task_start_human"
echo "Task ended:         $task_end_human"
echo "Task duration:      ${task_hours}h ${task_minutes}m ${task_seconds}s (${task_duration}s)"
echo "========================================="
echo "Files assigned:     $files_this_task"
echo "Files processed:    $total_processed"
echo "Successful runs:    $success_count"
echo "Failed runs:        $error_count"
echo "Total sim time:     ${total_sim_time}s"
echo "Average sim time:   ${avg_time}s"

if (( error_count > 0 )); then
    echo "Files that failed:"
    printf '  - %s\n' "${error_files[@]}"
    echo "Note: Failed files were skipped, but task completed successfully."
fi

# =============================================================================
# Write consolidated summary
# =============================================================================

{
    flock 200

    if [[ ! -f "$SUMMARY_FILE" ]]; then
        echo "job_id,task_id,hostname,start_time,end_time,duration_seconds,files_processed,successful,failed,total_sim_time,avg_sim_time" \
            > "$SUMMARY_FILE"
    fi

    echo "${job_id},${task_id},${HOSTNAME},${task_start_human},${task_end_human},${task_duration},${total_processed},${success_count},${error_count},${total_sim_time},${avg_time}" \
        >> "$SUMMARY_FILE"

} 200>"${SUMMARY_FILE}.lock"

echo "Timing data written to: $TIMING_FILE"
echo "Summary data appended to: $SUMMARY_FILE"
echo "Task $task_id exiting with success status"

exit 0