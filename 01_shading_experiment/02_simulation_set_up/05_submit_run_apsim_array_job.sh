#!/bin/bash -l
#SBATCH --partition=Long
#SBATCH --time=12-00:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2GB
#SBATCH --job-name=APX_prep

set -euo pipefail

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "APSIM manifest preparation/controller"
echo "Hostname:  $HOSTNAME"
echo "Started:   $(date)"
echo "Script:    $SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
echo "============================================================"

PREP_LOG_DIR="$SIMSETUP_SCRIPTS_DIR/logs/05_prepare_apsim_manifest"

if ! mkdir -p "$PREP_LOG_DIR"; then
    echo "ERROR: Could not create preparation log directory:"
    echo "  $PREP_LOG_DIR" >&2
    exit 1
fi

# =============================================================================
# Locate compute-node controller
# =============================================================================

CONTROLLER="$SIMSETUP_SCRIPTS_DIR/05_prepare_manifest_and_submit_array.sh"

if [[ ! -f "$CONTROLLER" ]]; then
    echo "ERROR: Controller script not found:"
    echo "  $CONTROLLER" >&2
    exit 1
fi

# =============================================================================
# Submit controller job
# =============================================================================

echo "Submitting APSIM manifest/controller job..."
echo "Controller: $CONTROLLER"
echo "Preparation logs: $PREP_LOG_DIR"

submit_output=$(
    sbatch \
        -o "$PREP_LOG_DIR/prepare_%j_output.txt" \
        -e "$PREP_LOG_DIR/prepare_%j_error.txt" \
        "$CONTROLLER"
)

echo "$submit_output"

if [[ $submit_output =~ Submitted\ batch\ job\ ([0-9]+) ]]; then

    controller_job_id="${BASH_REMATCH[1]}"

    echo "============================================================"
    echo "APSIM preparation job submitted"
    echo "Controller job ID: $controller_job_id"
    echo ""
    echo "The controller will:"
    echo "  1. Run on a compute node"
    echo "  2. Use the existing manifest if present"
    echo "  3. Otherwise create the manifest on the compute node"
    echo "  4. Submit the APSIM array"
    echo ""
    echo "Preparation output:"
    echo "  $PREP_LOG_DIR/prepare_${controller_job_id}_output.txt"
    echo "Preparation errors:"
    echo "  $PREP_LOG_DIR/prepare_${controller_job_id}_error.txt"
    echo "============================================================"

else

    echo "ERROR: Could not parse controller job ID from sbatch output:" >&2
    echo "$submit_output" >&2
    exit 1

fi