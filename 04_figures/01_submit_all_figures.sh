#!/bin/bash
# Run on the login node:  bash submit_all_figure_scripts.sh
# (no need to sbatch this file: it only submits the other jobs)

CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

SCRIPT_DIR="$FIGURE_SCRIPTS_DIR"
PYTHON="$HOME/micromamba/envs/my_micromamba_env/bin/python"   # the env's python, no micromamba run

cd "$SCRIPT_DIR" || exit 1
mkdir -p logs

for script in *fig*.py; do
    job_name="${script%.py}"

    echo "Submitting $script ($time_limit)"
    sbatch \
        --partition=Short \
        --job-name="$job_name" \
        --output="$SCRIPT_DIR/logs/${job_name}_%j.out" \
        --error="$SCRIPT_DIR/logs/${job_name}_%j.err" \
        --time="01:00:00" \
        --mem=8G \
        --cpus-per-task=1 \
        --wrap="cd '$SCRIPT_DIR' && '$PYTHON' '$script'"
done

echo "All figure jobs submitted."