#!/bin/bash -l
#SBATCH --partition=Short
#SBATCH --time=12:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2GB
#SBATCH --job-name=DB_prep

set -euo pipefail

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SCRIPT_DIR="$DRYLAND_DATAPROCESSING_SCRIPTS_DIR"

echo "============================================================"
echo "DB manifest preparation/controller"
echo "Hostname:  $HOSTNAME"
echo "Started:   $(date)"
echo "Script:    $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
echo "============================================================"

PREP_LOG_DIR="$SCRIPT_DIR/logs/01_prepare_db_manifest"

if ! mkdir -p "$PREP_LOG_DIR"; then
    echo "ERROR: Could not create preparation log directory:"
    echo "  $PREP_LOG_DIR" >&2
    exit 1
fi

# =============================================================================
# Locate compute-node controller
# =============================================================================

CONTROLLER="$SCRIPT_DIR/01_prepare_db_manifest_and_submit_conversion_array.sh"

if [[ ! -f "$CONTROLLER" ]]; then
    echo "ERROR: Controller script not found:"
    echo "  $CONTROLLER" >&2
    exit 1
fi

# =============================================================================
# Submit controller job
# =============================================================================

echo "Submitting DB manifest/controller job..."
echo "Controller: $CONTROLLER"
echo "Preparation logs: $PREP_LOG_DIR"

submit_output=$(
    sbatch \
        -o "$PREP_LOG_DIR/%j_prepare_output.txt" \
        -e "$PREP_LOG_DIR/%j_prepare_error.txt" \
        "$CONTROLLER"
)

echo "$submit_output"

if [[ $submit_output =~ Submitted\ batch\ job\ ([0-9]+) ]]; then

    controller_job_id="${BASH_REMATCH[1]}"

    echo "============================================================"
    echo "Converter preparation job submitted"
    echo "Controller job ID: $controller_job_id"
    echo ""
    echo "The controller will:"
    echo "  1. Run on a compute node"
    echo "  2. Use the existing manifest if present"
    echo "  3. Otherwise create the manifest of .db on the compute node"
    echo "  4. Submit the array to convert all .db files to .parquet files"
    echo ""
    echo "Preparation output:"
    echo "  $PREP_LOG_DIR/${controller_job_id}_prepare_output.txt"
    echo "Preparation errors:"
    echo "  $PREP_LOG_DIR/${controller_job_id}_prepare_error.txt"
    echo "============================================================"

else

    echo "ERROR: Could not parse controller job ID from sbatch output:" >&2
    echo "$submit_output" >&2
    exit 1

fi