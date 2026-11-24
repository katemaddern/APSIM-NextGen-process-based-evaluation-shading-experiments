#!/bin/bash
#SBATCH --job-name=apsim_met
#SBATCH --time=01:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

# ---------------------------------------------------------------------
# run_met_jobs.sbatch
#
# Finds every *.sim file in RAW_DIR and runs 01_adding_co2_observations_
# to_silo.py on each one as a separate SLURM array task, writing the
# CO2-appended .met files into OUT_DIR. CO2 fill values and the boundary
# year are left as the defaults baked into the python script itself.
#
# USAGE (run directly on the login/head node — NOT via `sbatch`):
#     ./run_met_jobs.sbatch
#
# All paths are hardcoded below for repeatability — edit them here,
# not on the command line.
# ---------------------------------------------------------------------

set -euo pipefail

# ---- Hardcoded paths: edit these, and only these ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

RAW_DIR="$SHADING_MET_RAW_DIR"                    # source *.sim files
OUT_DIR="$SHADING_MET_FILES_WITH_CO2"     # where output *.met files go
CO2_PATH="$CO2_PATH"
JOB_SCRIPT="01_adding_monthly_co2_observations_to_silo_kennaook.py"
IN_PATTERN="*.sim"

LOG_DIR="$MET_SCRIPTS_DIR/logs/01_add_co2_observations"

mkdir -p "$LOG_DIR" "$OUT_DIR"

# List of files lives in OUT_DIR so re-runs stay reproducible
FILELIST="$OUT_DIR/.sim_file_list.txt"

if [[ -z "${SLURM_ARRAY_TASK_ID:-}" ]]; then
    # ------------------- Top-level call: discover + resubmit -------------------
    if [[ ! -d "$RAW_DIR" ]]; then
        echo "Directory not found: $RAW_DIR" >&2
        exit 1
    fi
    if [[ ! -f "$JOB_SCRIPT" ]]; then
        echo "Job script not found: $JOB_SCRIPT" >&2
        exit 1
    fi
    if [[ ! -f "$CO2_PATH" ]]; then
        echo "CO2 file not found: $CO2_PATH" >&2
        exit 1
    fi

    find "$RAW_DIR" -maxdepth 1 -type f -name "$IN_PATTERN" | sort > "$FILELIST"
    N=$(wc -l < "$FILELIST")

    if [[ "$N" -eq 0 ]]; then
        echo "No $IN_PATTERN files found in $RAW_DIR" >&2
        exit 1
    fi

    echo "Found $N file(s) in $RAW_DIR"
    echo "Submitting array job with tasks 0-$((N - 1))"
    sbatch --array=0-$((N - 1)) \
        --output="$LOG_DIR/%x_%A_%a.out" \
        --error="$LOG_DIR/%x_%A_%a.err" \
        "$0"
    exit 0
fi

# ------------------------- Array task: process one file -------------------------
SIM_FILE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$FILELIST")

if [[ -z "$SIM_FILE" ]]; then
    echo "[Task $SLURM_ARRAY_TASK_ID] No file at this array index — skipping" >&2
    exit 1
fi

# If your cluster needs an explicit environment, uncomment and edit:
# module load python/3.11
# source activate apsim_env

echo "[Task $SLURM_ARRAY_TASK_ID] Processing: $SIM_FILE"
python3 "$JOB_SCRIPT" --co2 "$CO2_PATH" --input "$SIM_FILE" --outdir "$OUT_DIR"
