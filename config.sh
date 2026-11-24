#!/usr/bin/env bash
# ============================================================
# paper_1 workflow — central path configuration
#
# This is the ONLY file you should need to edit if directories
# move, get renamed, or you re-run this workflow on a different
# machine / scratch space in future.
#
# Every shell/sbatch script sources this file, and every python
# script imports it via config_loader.py, so both stay in sync.
# ============================================================

# ============================================================
# PATH/DATA LOCATION CONFIG
# ============================================================
# ---- Top-level locations -----------------------------------
# Where the scripts themselves live
export SCRIPTS_BASE="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments"
# Root scratch space (used for singularity bind mounts, and as the
# parent of the working data directory below)
export SCRATCH_BASE="$SCRATCH"
# Where the input/output data lives
export DATA_BASE="$SCRATCH_BASE/APSIM-NextGen-process-based-evaluation-shading-experiments"
#EXTERNAL Project space 1
export PROJECTS_ROOT="$PROJECT_SPACE"
export PROJECTS_BASE="$PROJECTS_ROOT/APSIM-NextGen-process-based-evaluation-shading-experiments"

# ---- Script subdirectories -----------------------------------
#Shading experiments
export SHADING_SCRIPTS_DIR="$SCRIPTS_BASE/01_shading_experiment"
export EXAMPLE_DATA_FILES_DIR="$SHADING_SCRIPTS_DIR/00_data_files"
export MET_SCRIPTS_DIR="$SHADING_SCRIPTS_DIR/01_met_file_processing"
export SIMSETUP_SCRIPTS_DIR="$SHADING_SCRIPTS_DIR/02_simulation_set_up"
export DATAPROCESSING_SCRIPTS_DIR="$SHADING_SCRIPTS_DIR/03_data_processing"
export SINGLE_SITE_DATAPROCESSING_SCRIPTS_DIR="$SHADING_SCRIPTS_DIR/03_data_processing_per_site"
#Dryland experiments
export DRYLAND_SCRIPTS_DIR="$SCRIPTS_BASE/02_dryland_shading_experiment"
export DRYLAND_EXAMPLE_DATA_FILES_DIR="$DRYLAND_SCRIPTS_DIR/00_data_files"
export DRYLAND_SIMSETUP_SCRIPTS_DIR="$DRYLAND_SCRIPTS_DIR/02_simulation_set_up"
export DRYLAND_DATAPROCESSING_SCRIPTS_DIR="$DRYLAND_SCRIPTS_DIR/03_data_processing"
#Data files for analysis and plotting
export ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR="$SCRIPTS_BASE/03_data_files_for_figures_and_tables"
#Scripts to make all figures in paper V2
export FIGURE_SCRIPTS_DIR="$SCRIPTS_BASE/04_figures"
#Scripts to make all tables in paper V2
export TABLE_SCRIPTS_DIR="$SCRIPTS_BASE/05_tables"

# ---- Data subdirectories -------------------------------------
#Container to run APSIM sims
export APSIM_CONTAINER_DIR="$DATA_BASE/apsim_container"

#Directory with processed files for analysis 
export PROCESSED_DATA_FILES_DIR="$DATA_BASE/processed_files_for_data_analysis"

#Experiment subdirectories 
#Shading experiment directory 
export SHADING_EXPERIMENT_DIR="$DATA_BASE/shading_experiment"
#Simulations directory, where all simulations are ran and located 
export SHADING_APSIM_SIMULATIONS_DIR="$SHADING_EXPERIMENT_DIR/apsim_simulations"
#Directory where all raw data on a daily timestep is kept (in parquet format so useable)
export SHADING_RAW_DATA_PARQUET_DIR="$SHADING_EXPERIMENT_DIR/all_raw_data_parquet_files"
#Directory where all processed and bound files go before data analysis 
export SHADING_PROCESSED_FILES_BEFORE_BINDING_DIR="$SHADING_EXPERIMENT_DIR/all_one_row_per_year_processed_files"
###### CHECK THIS AGAIN LATER - STILL exists 
#This probs needs deleting - simple bind and seeing_it_worked notebook using the directory
export SHADING_PROCESSED_FILES_FOR_ANALYSIS_DIR="$SHADING_EXPERIMENT_DIR/processed_files_for_data_analysis"
#Directories used in setting up simulations 
export SHADING_APSIM_TEMPLATES_BEFORE_CHECKING_DIR="$SHADING_EXPERIMENT_DIR/apsim_templates_before_checking"
export SHADING_APSIMX_TEMPLATES_FOR_DUPLICATION_DIR="$SHADING_EXPERIMENT_DIR/apsimx_templates_for_duplication"
export SHADING_MANIFEST_DIR="$SHADING_EXPERIMENT_DIR/file_manifests"
#Met files for sims, 
export SHADING_MET_FILES_DIR="$SHADING_EXPERIMENT_DIR/met_files"
## ---- met_files subdirectories ---------------------------------
export SHADING_MET_RAW_DIR="$SHADING_MET_FILES_DIR/raw_data"
export SHADING_MET_FILES_WITH_CO2="$SHADING_MET_FILES_DIR/met_files_with_co2_obs"
export SHADING_MET_OUT_DIR="$SHADING_MET_FILES_DIR/final_met_files_for_sims"
# .csv file with kennaook/cape grim monthly observations 
#(direct dowload from https://www.csiro.au/en/research/natural-environment/atmosphere/latest-greenhouse-gas-data, nothing changed)
export CO2_PATH="$SHADING_MET_RAW_DIR/CapeGrim_CO2_data_download.csv"

#Experiment subdirectories 
#Dryland shading experiment directory 
export DRYLAND_EXPERIMENT_DIR="$DATA_BASE/dryland_shading_experiment"
#Directories used in setting up simulations 
export DRYLAND_APSIM_TEMPLATES_BEFORE_CHECKING_DIR="$DRYLAND_EXPERIMENT_DIR/apsim_templates_before_checking"
export DRYLAND_APSIMX_TEMPLATES_FOR_DUPLICATION_DIR="$DRYLAND_EXPERIMENT_DIR/apsimx_templates_for_duplication"
#Manifest directory, used for setting up and running sims 
export DRYLAND_MANIFEST_DIR="$DRYLAND_EXPERIMENT_DIR/file_manifests"
#Simulations directory, where all simulations are ran and located 
export DRYLAND_APSIM_SIMULATIONS_DIR="$DRYLAND_EXPERIMENT_DIR/apsim_simulations"
#Directory where all raw data on a daily timestep is kept (in parquet format so useable)
export DRYLAND_RAW_DATA_PARQUET_DIR="$DRYLAND_EXPERIMENT_DIR/all_raw_data_parquet_files"
#Directory where all processed and bound files go before data analysis 
export DRYLAND_PROCESSED_FILES_BEFORE_BINDING_DIR="$DRYLAND_EXPERIMENT_DIR/all_one_row_per_year_processed_files"

### ---- Analysis output subdirectories -------------------------------------
##NOTE THIS IS HAPPENING IN PROJECTS, NOT SCRATCH
#All analysis ran off PROJECTS in case of server crash 
#Directory for first rough plots and data checking output
export INIITAL_ANALYSIS_OUTPUT_DIR="$PROJECTS_BASE/output_initial_data_analysis"
#Directory for storing data files for plotting (OCP data, opt practices etc. Any files that are not raw data but are used in figures goes here)
export ANALYSIS_OUTPUT_FOR_PLOTTING_DIR="$PROJECTS_BASE/processed_files_for_data_analysis"
#Directory for storing figures for the first draft of the paper
export FIRST_DRAFT_DIR="$PROJECTS_BASE/output_first_draft_plots_for_paper_revisions"

export SECOND_DRAFT_DIR="$PROJECTS_BASE/output_second_draft_plots_paper_revisions"

export DRYLAND_TEST_FIGS_DIR="$PROJECTS_BASE/output_dryland_test_figures"

# ---- commonly used things in sbatch scripts ---------------------------------
export FILES_PER_TASK=700 #60 when running 1 cultivar at a time, 750 if also running Scepter
export ARRAY_THROTTLE_DEFAULT=60

# ---- Frequently-used individual files --------------------------
# The apsim container image filename changes when you rebuild/update it —
# this is the one line to edit when that happens.
export APSIM_CONTAINER_SIF="$APSIM_CONTAINER_DIR/apsim_2026_09_8109_0.sif"
# APSIM manifest 
# Frozen list of .apsimx files used by the APSIM array job.
# The manifest is created on a compute node, not the login/head node.
export SHADING_APSIM_MANIFEST="$SHADING_MANIFEST_DIR/apsimx_files.manifest"
export SHADING_DB_MANIFEST="$SHADING_MANIFEST_DIR/db_files.manifest"
export SHADING_RAW_PARQUET_MANIFEST="$SHADING_MANIFEST_DIR/raw_parquet_files.manifest"

# The manifest is created on a compute node, not the login/head node.
export DRYLAND_APSIM_MANIFEST="$DRYLAND_MANIFEST_DIR/apsimx_files.manifest"
export DRYLAND_DB_MANIFEST="$DRYLAND_MANIFEST_DIR/db_files.manifest"
export DRYLAND_RAW_PARQUET_MANIFEST="$DRYLAND_MANIFEST_DIR/raw_parquet_files.manifest"

#Key results file used in analysis 
export ALL_DATA_SHADED_DF_FILE_NAME="shading_experiment_all_sites_all_data.parquet"
export DRYLAND_SHADED_DF_FILE_NAME="dryland_shading_experiment_all_sites_all_data.parquet"
export ALL_DATA_SHADED_DF="$PROCESSED_DATA_FILES_DIR/$ALL_DATA_SHADED_DF_FILE_NAME"
export DRYLAND_SHADED_DF="$PROCESSED_DATA_FILES_DIR/$DRYLAND_SHADED_DF_FILE_NAME"

export LIMITED_SHADED_DF_FILE_NAME="shading_experiment_all_sites_limited_variables_for_upload.parquet"
export LIMITED_DRYLAND_SHADED_DF_FILE_NAME="dryland_shading_experiment_all_sites_limited_variables_for_upload.parquet"

export LIMITED_SHADED_DF="$ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR/$LIMITED_SHADED_DF_FILE_NAME"
export LIMITED_DRYLAND_SHADED_DF="$ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR/$LIMITED_DRYLAND_SHADED_DF_FILE_NAME"

# ---- Frequently-used analysis varibles --------------------------
export EXAMPLE_CULTIVAR="SpringQM"
export EXAMPLE_SITE="lameroo"

# ---- Shared workflow settings -----------------------------------
export IN_PATTERN="*.sim"

# ============================================================
# SET UP for  (copies of DATA_BASE, see 12_copy_data_to_other_locations.sh)
# ============================================================
# Directories (names relative to DATA_BASE) to copy. Comma-separated,
# no spaces, same style as SITE_ORDER. Edit this line to copy more.
export COPY_DIRS="processed_files_for_data_analysis"

# Where 12_copy_data_to_other_locations.sh writes its timestamped logs + ledger
export COPY_LOG_DIR="$DATAPROCESSING_SCRIPTS_DIR/logs/11_copy_files_to_other_locations"

# ---- Site list --------------------------------------------------
# Used across multiple job scripts (met processing, sim set-up, apsim
# runs). Edit this ONE list if sites are added/removed/renamed.
#
# NOTE: this is a plain bash array, not `export`ed — bash cannot export
# arrays reliably, so config_loader.py (python) will NOT see this
# variable. Shell scripts get it automatically via `source config.sh`.
# If a python script ever needs the same list, either hardcode it there
# too, or ask to move it into a shared sites.txt / sites.json file that
# both bash and python can read — flag this if/when that comes up.
SITE_LIST=(
    'waikerie' 
    'mildura'
    'lameroo'
    'birchip' 
    'longerenong' 
    'bordertown' 
    'lakebolac' 
    'millicent'
)

# ------------------------------------------------------------
# NOTE for future edits:
#   - Keep this file to simple `export VAR="value"` lines.
#   - You CAN reference earlier variables (e.g. "$DATA_BASE/subdir"),
#     but avoid loops, conditionals, or command substitution —
#     config_loader.py re-sources this file with plain bash and
#     expects a flat list of exported variables.
#   - Do not rename existing variables without also updating any
#     scripts that reference them (grep for the name across
#     01_met_file_processing/ and 02_simulation_set_up/ first).
# ------------------------------------------------------------