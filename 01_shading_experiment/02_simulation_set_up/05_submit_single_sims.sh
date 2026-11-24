#!/bin/bash -l
#SBATCH --partition=Long
#SBATCH --time=12-00:00:00
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=2GB
#SBATCH --cpus-per-task=1
#SBATCH --job-name=APX_sites

# Usage:
#   sbatch run_apsim_sites.sh site_name_1 site_name_2 ...
#   sbatch run_apsim_sites.sh $(cat rerun_sites.txt)
#   (or leave arguments empty to use the hardcoded sites list below)
#
# Site names are file names without ".apsimx" (the extension is tolerated).
# Works as a single job or as an array job (--array=0-N), chunked by FILES_PER_TASK.

set -uo pipefail

# =============================================================================
# Config
# =============================================================================

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SIM_DIR="$SHADING_APSIM_SIMULATIONS_DIR"
CONTAINER="$APSIM_CONTAINER_SIF"
files_per_task="$FILES_PER_TASK"

# Resolve the real path behind the scratch symlink.
SCRATCH_REAL=$(readlink -f "$SCRATCH_BASE")

# =============================================================================
# SLURM variables
# =============================================================================

job_id=${SLURM_ARRAY_JOB_ID:-${SLURM_JOB_ID:-"local"}}
task_id=${SLURM_ARRAY_TASK_ID:-0}

# =============================================================================
# Log redirection
# =============================================================================

LOG_DIR="$SIMSETUP_SCRIPTS_DIR/logs/05_single_sims_rerun"

if mkdir -p "$LOG_DIR"; then
    exec > "${LOG_DIR}/apsim_rerun_${job_id}_${task_id}.out" \
        2> "${LOG_DIR}/apsim_rerun_${job_id}_${task_id}.err"
else
    echo "WARNING: Could not create log directory $LOG_DIR; logging to default SLURM output." >&2
fi

# =============================================================================
# Site list
# =============================================================================

if (( $# > 0 )); then
    sites=("$@")
else
    sites=(
            waikerie_1996_radiation_shading_67_296_SpringMS
            waikerie_1997_radiation_shading_67_365_SpringVQQ
            waikerie_1998_radiation_shading_67_297_SpringQ
            waikerie_2001_radiation_shading_67_200_SpringM
            waikerie_2002_radiation_shading_67_155_WinterM
            waikerie_2005_radiation_shading_67_131_WinterVS
            waikerie_2005_radiation_shading_67_247_SpringVS
            waikerie_2006_radiation_shading_67_159_WinterM
            waikerie_2007_radiation_shading_67_344_WinterQ
            waikerie_2008_radiation_shading_67_162_WinterQ
    )
fi

# When not run as an array, process the whole list in this one task.
if [[ -z "${SLURM_ARRAY_TASK_ID:-}" ]]; then
    files_per_task=${#sites[@]}
fi

echo "Job ID:      $job_id"
echo "Task ID:     $task_id"
echo "Hostname:    $HOSTNAME"

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

if [[ ! -f "$CONTAINER" ]]; then
    echo "ERROR: APSIM container does not exist: $CONTAINER" >&2
    exit 1
fi

if [[ ! -d "$SIM_DIR" ]]; then
    echo "ERROR: Simulation directory does not exist: $SIM_DIR" >&2
    exit 1
fi

if (( files_per_task < 1 )); then
    echo "ERROR: FILES_PER_TASK must be >= 1. Got: $files_per_task" >&2
    exit 1
fi

if (( ${#sites[@]} == 0 )); then
    echo "ERROR: No site names given." >&2
    exit 1
fi

# =============================================================================
# Scratch tmp
# =============================================================================

SCRATCH_TMP="${SCRATCH_BASE}/apsim_tmp_${job_id}_${task_id}"

cleanup_scratch_tmp() {
    if [[ -d "$SCRATCH_TMP" ]]; then
        rm -rf "$SCRATCH_TMP"
        echo "Scratch tmp cleaned up: $SCRATCH_TMP"
    fi
}

trap cleanup_scratch_tmp EXIT

if ! mkdir -p "$SCRATCH_TMP"; then
    echo "ERROR: Could not create scratch tmp directory: $SCRATCH_TMP" >&2
    exit 1
fi

export TMPDIR="${SCRATCH_TMP}"

echo "Scratch tmp:  $SCRATCH_TMP (bound to container /tmp)"

# =============================================================================
# Build file list from site names
# =============================================================================

all_files=()

for site in "${sites[@]}"; do
    site="${site%.apsimx}"
    candidate="${SIM_DIR}/${site}.apsimx"

    # Fall back to searching subdirectories if not directly in SIM_DIR.
    if [[ ! -f "$candidate" ]]; then
        match=$(find "$SIM_DIR" -name "${site}.apsimx" -print -quit 2>/dev/null)
        [[ -n "$match" ]] && candidate="$match"
    fi

    all_files+=("$candidate")
done

total_files=${#all_files[@]}

# =============================================================================
# Determine this task's file range
# =============================================================================

start_idx=$((task_id * files_per_task))
end_idx=$((start_idx + files_per_task - 1))

if (( start_idx >= total_files )); then
    echo "Array task $task_id has no work (start_idx=$start_idx, total_files=$total_files)."
    exit 0
fi

if (( end_idx >= total_files )); then
    end_idx=$((total_files - 1))
fi

files_this_task=$((end_idx - start_idx + 1))
files=("${all_files[@]:start_idx:files_this_task}")

echo "Container:    $CONTAINER"
echo "Sim dir:      $SIM_DIR"
echo "Files assigned to this task: $files_this_task"

# =============================================================================
# Run simulations
# =============================================================================

success_count=0
error_count=0
error_files=()

for filepath in "${files[@]}"; do

    insite="$(basename "$filepath" .apsimx)"

    echo "============================================================"
    echo "Running: $insite"
    echo "File:    $filepath"
    echo "============================================================"

    if [[ ! -f "$filepath" ]]; then
        echo "ERROR: File does not exist: $filepath" >&2
        error_count=$((error_count + 1))
        error_files+=("$insite")
        continue
    fi

    if "$SINGULARITY" run \
        --env TMPDIR=/tmp \
        -B "${SIM_DIR}:${SIM_DIR}" \
        -B "${SCRATCH_BASE}:${SCRATCH_BASE}" \
        -B "${SCRATCH_REAL}:${SCRATCH_REAL}" \
        -B "${SCRATCH_TMP}:/tmp" \
        "$CONTAINER" \
        "$filepath"; then
        success_count=$((success_count + 1))
        echo "SUCCESS: $insite"
    else
        exit_code=$?
        error_count=$((error_count + 1))
        error_files+=("$insite")
        echo "ERROR: $insite (exit code: $exit_code)" >&2
    fi

done

# =============================================================================
# Summary
# =============================================================================

echo "========================================="
echo "Task $task_id finished on $HOSTNAME"
echo "Successful runs: $success_count"
echo "Failed runs:     $error_count"

if (( error_count > 0 )); then
    echo "Files that failed:"
    printf '  - %s\n' "${error_files[@]}"
fi

exit 0