#!/bin/bash

# ---- Hardcoded paths: edit these, and only these ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$MET_SCRIPTS_DIR/logs/03_make_control_met_files"
mkdir -p "$LOG_DIR"

MET_DIR="$SHADING_MET_FILES_WITH_CO2"

for filepath in "$MET_DIR"/*.met; do
    insite=$(basename "$filepath")

    echo "Submitting: $insite"
    sbatch \
        --partition=Short \
        --time=12:00:00  \
        --job-name=CONT${insite} \
        --ntasks=1 \
        --mem=10GB \
        -e ${LOG_DIR}/%j_${insite}_error_%j.txt \
        -o ${LOG_DIR}/%j_${insite}_output_%j.txt \
        --wrap="python -u 03_met_file_radiation_modifer_control_NO_MODS.py $insite"
done

