#!/bin/bash

# ---- Hardcoded paths: edit these, and only these ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$MET_SCRIPTS_DIR/logs/02_modify_met_files_shading_period"
mkdir -p "$LOG_DIR"

MET_DIR="$SHADING_MET_FILES_WITH_CO2"

for filepath in "$MET_DIR"/*.met; do
    insite=$(basename "$filepath")

    echo "Submitting: $insite"
    sbatch \
        --partition=Short \
        --time=12:00:00  \
        --job-name=RADN${insite} \
        --ntasks=1 \
        --mem=10GB \
        -e ${LOG_DIR}/%j_${insite}_error_%j.txt \
        -o ${LOG_DIR}/%j_${insite}_output_%j.txt \
        --wrap="python -u 02_met_file_radiation_modifer.py $insite"
done

