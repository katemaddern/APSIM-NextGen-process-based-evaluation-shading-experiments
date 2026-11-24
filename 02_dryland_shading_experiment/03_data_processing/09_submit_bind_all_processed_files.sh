#!/bin/bash

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$DRYLAND_DATAPROCESSING_SCRIPTS_DIR/logs/09_bind_all_processed_files"
SCRIPT="$DRYLAND_DATAPROCESSING_SCRIPTS_DIR/09_bind_all_processed_files.py"

mkdir -p "$LOG_DIR"

# SITE_LIST=('waikerie')

for insite in "${SITE_LIST[@]}"; do
    echo "Running for site: $insite"
    sbatch \
        --partition=Short \
        --time=12:00:00 \
        --job-name=BIND${insite} \
        --ntasks=1 \
        --cpus-per-task=16 \
        --mem=64GB \
        -e ${LOG_DIR}/%j_${insite}_error.txt \
        -o ${LOG_DIR}/%j_${insite}_output.txt \
        --wrap="python -u $SCRIPT $insite"
done