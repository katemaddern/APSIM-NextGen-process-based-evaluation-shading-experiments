#!/bin/bash

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

LOG_DIR="$DATAPROCESSING_SCRIPTS_DIR/logs/11_make_and_save_limited_data_set"

mkdir -p "$LOG_DIR"

sbatch \
    --partition=Short \
    --time=12:00:00 \
    --job-name=LIMITED_DF \
    --ntasks=1 \
    --mem=20GB \
    -e ${LOG_DIR}/%j_LIMITED_DF_error_%j.txt \
    -o ${LOG_DIR}/%j_LIMITED_DF_output_%j.txt \
    --wrap="echo Running on node: \$HOSTNAME at \$(date); python 11_cut_data_file_back_and_upload_to_script_dir.py"
