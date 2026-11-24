#!/bin/bash

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$DRYLAND_DATAPROCESSING_SCRIPTS_DIR/logs/03_check_parquet_shapes"

mkdir -p "$LOG_DIR"

# SITE_LIST=('lameroo')

for site in "${SITE_LIST[@]}"; do
    echo "Running for site: $site"
    sbatch \
        --partition=Short \
        --time=12:00:00 \
        --job-name=PQC${site} \
        --ntasks=1 \
        --mem=10GB \
        -e ${LOG_DIR}/%j_${site}_error_%j.txt \
        -o ${LOG_DIR}/%j_${site}_output_%j.txt \
        --wrap="python 03_parquet_shape_check.py $site --expected-rows 424 --max-rows 425"
done