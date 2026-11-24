#!/bin/bash
#set -x

# ---- Load shared path configuration ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$DRYLAND_SIMSETUP_SCRIPTS_DIR/logs/03_replicate_control_sims"
mkdir -p "$LOG_DIR"

for insite in "${SITE_LIST[@]}"; do
    echo "Running for site: $insite"
    sbatch \
        --partition=Short \
        --time=8:00:00 \
        --job-name=REP_${insite} \
        --ntasks=1 \
        --mem=30GB \
        -e ${LOG_DIR}/%j_${insite}_test_error_%j.txt \
        -o ${LOG_DIR}/%j_${insite}_test_output_%j.txt \
        --wrap="echo Running on node: \$HOSTNAME at \$(date); python 03_replicate_control_sims.py $insite"
done
