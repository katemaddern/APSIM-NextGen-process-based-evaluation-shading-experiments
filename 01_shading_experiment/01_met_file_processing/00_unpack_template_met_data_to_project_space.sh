#!/bin/bash
# ---------------------------------------------------------------------
#
# USAGE:
#     ./unpack_template_data.sh
#
# All paths are hardcoded below for repeatability — edit them here,
# not on the command line.
# ---------------------------------------------------------------------

set -euo pipefail

# ---- Config file unfortunately hard coded ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

EXAMPLE_DATA_FILES_DIR="$EXAMPLE_DATA_FILES_DIR"
DEST_DIR="$SHADING_MET_RAW_DIR"

FILES=(
    "CapeGrim_CO2_data_download.csv"
    "waikerie_24018.sim"
    "mildura_76031.sim"
    "lameroo_25509.sim"
    "birchip_77008.sim"
    "bordertown_25501.sim"
    "longerenong_79028.sim"
    "millicent_26018.sim"
    "lakebolac_89016.sim"
)

# ---- Copy ----
mkdir -p "$DEST_DIR"

for f in "${FILES[@]}"; do
    if [[ -f "$EXAMPLE_DATA_FILES_DIR/$f" ]]; then
        cp -vn "$EXAMPLE_DATA_FILES_DIR/$f" "$DEST_DIR/"
    else
        echo "WARNING: $EXAMPLE_DATA_FILES_DIR/$f not found" >&2
    fi
done

echo "Done: files copied to $DEST_DIR"