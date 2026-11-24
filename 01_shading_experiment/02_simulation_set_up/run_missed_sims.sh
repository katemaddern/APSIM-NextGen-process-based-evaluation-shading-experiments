#!/bin/bash
#set -x
# Run the APSIM simulations listed in problem_files_<site>.txt, one job per site,
# using 05_run_apsim_array.sh in its APSIM_FILE_LIST mode (no changes needed to it).

# ---- Load shared path configuration ----
CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh"
source "$CONFIG_PATH"

PROBLEM_DIR="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/01_shading_experiment/02_simulation_set_up"
RUN_SCRIPT="$PROBLEM_DIR/05_run_apsim_array.sh"

# 0 = one task per site runs that site's whole list.
# Set e.g. 10 to split each site's list into array tasks of 10 sims (runs in parallel).
MAX_FILES_PER_TASK=0

LOG_DIR="$SIMSETUP_SCRIPTS_DIR/logs/run_missed_sims"
LIST_DIR="$LOG_DIR/name_lists"
mkdir -p "$LOG_DIR" "$LIST_DIR"

if [[ ! -f "$RUN_SCRIPT" ]]; then
    echo "ERROR: run script not found: $RUN_SCRIPT" >&2
    exit 1
fi

for insite in "${SITE_LIST[@]}"; do
    problem_file="$PROBLEM_DIR/problem_files_${insite}.txt"

    if [[ ! -s "$problem_file" ]]; then
        echo "Site $insite: no problem file (or empty) - skipping"
        continue
    fi

    # problem_files lines are STATUS<tab>NAME<tab>DETAIL -> keep NAME, one per line, no duplicates
    name_list="$LIST_DIR/missed_sims_${insite}.txt"
    cut -f2 "$problem_file" | tr -d '\r' | grep -v '^[[:space:]]*$' | awk '!seen[$0]++' > "$name_list"

    n=$(wc -l < "$name_list")
    if (( n == 0 )); then
        echo "Site $insite: no simulation names found in $problem_file - skipping"
        continue
    fi

    if (( MAX_FILES_PER_TASK > 0 )); then
        per=$MAX_FILES_PER_TASK
    else
        per=$n
    fi
    ntasks=$(( (n + per - 1) / per ))

    echo "Site $insite: $n simulations -> $ntasks task(s) of up to $per (list: $name_list)"
    sbatch \
        --job-name=APXFIX_${insite} \
        --array=0-$((ntasks - 1)) \
        --export=ALL,APSIM_FILE_LIST="$name_list",APSIM_FILES_PER_TASK=$per \
        -o "$LOG_DIR/%A_%a_${insite}_output.txt" \
        -e "$LOG_DIR/%A_%a_${insite}_error.txt" \
        "$RUN_SCRIPT"
done