#!/bin/bash
#set -x

# ---- Load shared path configuration ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

# SCRATCH_REAL resolves symlinks at runtime (machine-dependent), so it's
# computed here rather than stored in config.sh.
SCRATCH_REAL=$(readlink -f "$SCRATCH_BASE")

SIM_DIR="$DRYLAND_APSIM_TEMPLATES_BEFORE_CHECKING_DIR"
CONTAINER="$APSIM_CONTAINER_SIF"

LOG_DIR="$DRYLAND_SIMSETUP_SCRIPTS_DIR/logs/01_template_test"
mkdir -p "$LOG_DIR"

echo "attempting to find files in $SIM_DIR"

shopt -s nullglob                     # empty array (not a literal "*.apsimx") if no matches
files=("$SIM_DIR"/*.apsimx)

if (( ${#files[@]} == 0 )); then
    echo "No .apsimx files found in $SIM_DIR"
    exit 1
fi

echo "Found ${#files[@]} .apsimx files"

for filepath in "${files[@]}"; do
    insite=$(basename "$filepath" .apsimx)
    echo "Running for site: $insite"

    sbatch --partition=Short --time=2:00:00 --ntasks=1 --mem=2GB --job-name="APX${insite}" \
        -e "${LOG_DIR}/%j_${insite}_error.txt" \
        -o "${LOG_DIR}/%j_${insite}_output.txt" \
        --wrap="echo Running on node: \$HOSTNAME at \$(date); singularity run \
            -B ${SCRATCH_BASE}:${SCRATCH_BASE} \
            -B ${SCRATCH_REAL}:${SCRATCH_REAL} \
            ${CONTAINER} ${filepath}"
done