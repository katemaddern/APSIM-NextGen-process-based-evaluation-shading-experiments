#!/bin/bash
#
# Submits one independent SLURM job per site listed in SITE_LIST below.
# Run this directly with `bash 12_run_single_apsim_sims.sh` (do NOT sbatch this
# script itself — it just calls sbatch once per site).

set -uo pipefail

# =============================================================================
# Config
# =============================================================================
 
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"
 
SIM_DIR="$SHADING_RAW_DATA_PARQUET_DIR"
 
# .parquet files store the weather file path in whatever form they were
# authored with — this may be the symlinked scratch path (SCRATCH_BASE,
# e.g. /home/.../scratch) rather than the resolved real path. Bind
# both forms so absolute paths referenced from inside the .db (weather
# files, etc.) resolve correctly no matter which form is used.
SCRATCH_REAL=$(readlink -f "$SCRATCH_BASE")
 
SITE_LIST=(
'birchip_1995_radiation_shading_67_182_WinterVQ'
'birchip_1995_radiation_shading_67_241_SpringVS'
'birchip_1995_radiation_shading_67_357_WinterQ'
'birchip_1996_radiation_shading_67_352_SpringQM'
'birchip_1998_radiation_shading_67_295_WinterM'
'birchip_2000_radiation_shading_67_167_WinterQ'
'birchip_2002_radiation_shading_67_331_SpringQM'
)
 
LOG_DIR="$DATAPROCESSING_SCRIPTS_DIR/logs/08_rerun_single_data_processing"
mkdir -p "$LOG_DIR"
 
# =============================================================================
# Checks
# =============================================================================
  
if [[ ! -d "$SIM_DIR" ]]; then
    echo "ERROR: Simulation directory does not exist: $SIM_DIR" >&2
    exit 1
fi
 
# =============================================================================
# Submit one job per site
# =============================================================================
 
echo "Submitting ${#SITE_LIST[@]} single-site jobs..."
echo "============================================================"
 
for insite in "${SITE_LIST[@]}"; do
 
    # Resolve the .db path now, at submission time, so a missing/duplicate
    # file is caught immediately rather than after the job starts running.
    matches=()
    while IFS= read -r -d '' match; do
        matches+=("$match")
    done < <(find "$SIM_DIR" -type f -name "${insite}.parquet" -print0)
 
    if [[ ${#matches[@]} -eq 0 ]]; then
        echo "SKIP: No .parquet file found for site: $insite (searched $SIM_DIR)" >&2
        continue
    fi
 
    if [[ ${#matches[@]} -gt 1 ]]; then
        echo "SKIP: Multiple .parquet files found for site: $insite" >&2
        printf '  %s\n' "${matches[@]}" >&2
        continue
    fi
 
    filepath="${matches[0]}"
 
    echo "Submitting: $insite"
    echo "  File: $filepath"
 
    sbatch \
        --partition=Short \
        --time=2:00:00 \
        --ntasks=1 \
        --mem-per-cpu=2GB \
        --cpus-per-task=1 \
        --job-name="PROCESS_${insite}" \
        -e "${LOG_DIR}/%j_${insite}_%j_error.txt" \
        -o "${LOG_DIR}/%j_${insite}_%j_output.txt" \
        --wrap="python 05_one_line_per_sim_processor.py $insite"
 
done
 
echo "============================================================"
echo "Submission complete."