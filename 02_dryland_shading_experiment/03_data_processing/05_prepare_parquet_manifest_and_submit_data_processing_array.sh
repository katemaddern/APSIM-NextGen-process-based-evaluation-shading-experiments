#!/bin/bash -l
#SBATCH --partition=Short
#SBATCH --time=12:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2GB
#SBATCH --job-name=PQ_manifest_prepare

set -euo pipefail

# =============================================================================
# Config
# =============================================================================

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SCRIPT_DIR="$DRYLAND_DATAPROCESSING_SCRIPTS_DIR"

PARQUET_DIR="$DRYLAND_RAW_DATA_PARQUET_DIR"
MANIFEST="$DRYLAND_RAW_PARQUET_MANIFEST"

files_per_task="$FILES_PER_TASK"
throttle="${THROTTLE:-$ARRAY_THROTTLE_DEFAULT}"

# =============================================================================
# Basic checks
# =============================================================================

echo "============================================================"
echo "Raw Parquet manifest preparation/controller"
echo "Hostname:  $HOSTNAME"
echo "Started:   $(date)"
echo "============================================================"

if [[ ! -d "$PARQUET_DIR" ]]; then
    echo "ERROR: Simulation directory does not exist:"
    echo "  $PARQUET_DIR"
    exit 1
fi

if (( files_per_task < 1 )); then
    echo "ERROR: FILES_PER_TASK must be >= 1. Got: $files_per_task"
    exit 1
fi

if (( throttle < 1 )); then
    echo "ERROR: THROTTLE must be >= 1. Got: $throttle"
    exit 1
fi

# =============================================================================
# Create manifest directory
# =============================================================================

MANIFEST_DIR="$(dirname "$MANIFEST")"

if ! mkdir -p "$MANIFEST_DIR"; then
    echo "ERROR: Could not create manifest directory:"
    echo "  $MANIFEST_DIR"
    exit 1
fi

# =============================================================================
# Create manifest ONLY if it does not already exist
# =============================================================================

if [[ -f "$MANIFEST" ]]; then

    echo "Manifest already exists."
    echo "NOT recreating it."
    echo "Manifest: $MANIFEST"

else

    echo "Manifest does not exist."
    echo "Creating manifest on compute node..."
    echo "Simulation directory: $PARQUET_DIR"
    echo "This may take some time for a very large directory."

    tmp_manifest="${MANIFEST}.tmp.${SLURM_JOB_ID}"
    trap 'rm -f "$tmp_manifest"' EXIT
    rm -f "$tmp_manifest"

    echo "Compute node /tmp usage:"
    df -h /tmp
    echo "TMPDIR is set to: ${TMPDIR:-<unset>}"

    find "$PARQUET_DIR" \
        -maxdepth 1 \
        -type f \
        -name '*.parquet' \
        -print |
        sort -T "$MANIFEST_DIR" > "$tmp_manifest"

    if [[ ! -s "$tmp_manifest" ]]; then
        echo "ERROR: Manifest creation produced no .parquet files." >&2
        rm -f "$tmp_manifest"
        exit 1
    fi

    # Atomic replacement: the completed manifest becomes visible in one move.
    mv "$tmp_manifest" "$MANIFEST"

    echo "Manifest created successfully:"
    echo "  $MANIFEST"
fi

# =============================================================================
# Check manifest
# =============================================================================

total_files=$(wc -l < "$MANIFEST")

echo "Manifest contains: $total_files files"

if (( total_files == 0 )); then
    echo "ERROR: Manifest is empty:"
    echo "  $MANIFEST"
    exit 1
fi

# =============================================================================
# Compute array size from manifest
# =============================================================================

num_tasks=$(( (total_files + files_per_task - 1) / files_per_task ))

echo "Files per task:                 $files_per_task"
echo "Array tasks:                    $num_tasks"
echo "Maximum concurrent array tasks: $throttle"

# =============================================================================
# Create logs
# =============================================================================

LOG_DIR="$SCRIPT_DIR/logs/05_process_raw_parquet_to_one_line_per_year"

if ! mkdir -p "$LOG_DIR"; then
    echo "ERROR: Could not create log directory:"
    echo "  $LOG_DIR"
    exit 1
fi

# =============================================================================
# Submit Parquet file array
# =============================================================================

ARRAY_SCRIPT="$SCRIPT_DIR/05_sim_data_processing_array.sh"

if [[ ! -f "$ARRAY_SCRIPT" ]]; then
    echo "ERROR: Array script not found:"
    echo "  $ARRAY_SCRIPT"
    exit 1
fi

echo "Submitting .parquet processing array..."

submit_output=$(
    sbatch \
        --array="0-$((num_tasks - 1))%${throttle}" \
        -e "$LOG_DIR/array_%A_%a_error.txt" \
        -o "$LOG_DIR/array_%A_%a_output.txt" \
        "$ARRAY_SCRIPT"
)

echo "$submit_output"

if [[ $submit_output =~ Submitted\ batch\ job\ ([0-9]+) ]]; then

    array_job_id="${BASH_REMATCH[1]}"

    echo "============================================================"
    echo "Raw Parquet processing array submitted successfully"
    echo "Array job ID:        $array_job_id"
    echo "Array tasks:         0-$((num_tasks - 1))"
    echo "Files:               $total_files"
    echo "Files per task:      $files_per_task"
    echo "Max concurrent:      $throttle"
    echo "Manifest:            $MANIFEST"
    echo "============================================================"

else

    echo "ERROR: Could not parse array job ID from sbatch output:"
    echo "$submit_output"
    exit 1

fi
