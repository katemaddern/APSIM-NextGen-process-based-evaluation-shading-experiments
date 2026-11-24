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

EXAMPLE_DATA_FILES_DIR="$DRYLAND_EXAMPLE_DATA_FILES_DIR"
DEST_DIR="$DRYLAND_APSIM_TEMPLATES_BEFORE_CHECKING_DIR"

FILES=(
    "waikerie_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "waikerie_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "mildura_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "mildura_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "lameroo_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "lameroo_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "birchip_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "birchip_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "bordertown_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "bordertown_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "longerenong_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "longerenong_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "millicent_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "millicent_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
    "lakebolac_2024_control_drylandcontrol_0_0_SpringVQQ.apsimx"
    "lakebolac_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
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