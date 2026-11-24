#!/bin/bash

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$DATAPROCESSING_SCRIPTS_DIR/logs/10_merge_all_sites"

mkdir -p "$LOG_DIR"

sbatch \
    --partition=Short \
    --time=12:00:00 \
    --job-name=BINDSITES \
    --ntasks=1 \
    --mem=200GB \
    -e ${LOG_DIR}/%j_BINDSITES_error_%j.txt \
    -o ${LOG_DIR}/%j_BINDSITES_output_%j.txt \
    --wrap="echo Running on node: \$HOSTNAME at \$(date); python 10_merge_all_sites.py"
