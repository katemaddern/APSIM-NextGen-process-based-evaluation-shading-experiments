#!/bin/bash

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$SIMSETUP_SCRIPTS_DIR/logs/06_check_db_files_created"

mkdir -p "$LOG_DIR"

SITE_LIST=('waikerie')

for site in "${SITE_LIST[@]}"; do
    echo "Running for site: $site"
    sbatch \
        --partition=Short \
        --time=12:00:00 \
        --job-name=DBC${site} \
        --ntasks=1 \
        --mem=10GB \
        -e ${LOG_DIR}/%j_${site}_error_%j.txt \
        -o ${LOG_DIR}/%j_${site}_output_%j.txt \
        --wrap="python3 06_db_file_check.py $site"
done