Things still needed: 
- A directory set up script to run at the start to make all of the data folders 
- A well written thing of where and how I got the template files (APSOIL number for Lameroo really needed)
- Need a tidy environment once finished with only the required packages, add setting up this environment into the directory set up script
- Also maybe in set up script do a find and replace for hard coded config file location
- Maybe an all in one run script

-Users need to update $HOME, $SCRATCH and $PROJECTS in the config file, also will need to set up the met file directory in the .apsimx files - all are currently set to $SCRATCH

-Config file is hard coded to CONFIG_PATH="$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/config.sh" - sorry that you'll have to change that 

- All met file locations in the .asimx files are currently set to $SCRATCH_BASE/APSIM-NextGen-process-based-evaluation-shading-experiments - that won't work as the container requires a hard file parth. Will need to be manually updated before running it

-Need to unpack/move Fischer data to the correct directory 


#Here need to include 
- VITAL TO HAVE THE CONTROL RADIATION DURING THE SHADING PERIODS SAVED SOMEWHERE, AS AVERAGE PERSON WON'T HAVE THE DAILY DATA
#Important to not have Apptainer as a part of your virtual environment 

-Need to include APSIM version used 
- file naming convention and the progression of file names

- Break this into 2 sections: 1. If you are looking to understand the paper, the key scripts are x, y and z. Go here. Stats testing for each plot is in the plot code etc 
-                              2. If you are looking to run this pipeline for yourself, see below. 

- something to say what output directories are needed/ideally a script that pulls off config to make them for a given base

- Maybe include apsim inital conditions files

- template files/raw data 
    - yaml micromamba environment
    - lameroo met file Station Number 025590 from https://www.longpaddock.qld.gov.au/silo/point-data/ ; downloaded 2026-09-29 
    - kennanook co2 observations https://www.csiro.au/en/research/natural-environment/atmosphere/latest-greenhouse-gas-data downloaded 2026-09-29 
    - Apsim NextGen Files - from $HOME/APSIM-NextGen-process-based-evaluation-shading-experiments/01_shading_experiment/apsimx_templates_for_duplication
    - Maybe make a separate/individual soil file or link to APSOIL database 
    - Digitised Fischer Data 

- Fischer data for plotting 


#How to run scripts 
- Basic statement about this workflow is designed to work on a linux HPC cluster, all code is written in python/bash
- My cluster works that having the environment open on the head node at submission replicates the environment for each task, the environment is not being set in any of the submission scripts
- sbatch file with .sh and 'submit' in the name, follow the numbers
- Need to say that the files in 00_data_files need to be manally copied to the following locations.
    Scripts are set up to run with datafiles in the data storage space so eveything runs faster 
- Copy of the templates from the check directory to the to be duplicated folder needs to be done manually 
    - not written into scripts as it is an important point to check that the template sims have worked and given good outputs

- Unfortunately config file had to be hard coded into bash scripts, but is exactly the same so can find and replace all hopefully


###SCRIPTS LAYOUT########

paper_1/                                   $SCRIPTS_BASE
├── config.sh                              central path config
├── config_loader.py                       allows for the bash config locations to work in python scripts, home of 'cfg' function
└── 01_shading_experiment/                 $SHADING_SCRIPTS_DIR
    ├── 00_data_files/                     $EXAMPLE_DATA_FILES_DIR
    ├── 01_met_file_processing/            $MET_SCRIPTS_DIR
    ├── 02_simulation_set_up/              $SIMSETUP_SCRIPTS_DIR
    └── 03_data_processing/                $DATAPROCESSING_SCRIPTS_DIR

###DATA LAYOUT########

paper_1_final/                                    $DATA_BASE
├── apsim_container/                              $APSIM_CONTAINER_DIR
│   └── apsim_2026_09_8109_0.sif          [1]     $APSIM_CONTAINER_SIF
└── shading_experiment/                           $SHADING_EXPERIMENT_DIR
    ├── met_files/                                $SHADING_MET_FILES_DIR
    │   ├── raw_data/                             $SHADING_MET_RAW_DIR
    │   │   └── CapeGrim_CO2_data_download.csv [2] $CO2_PATH
    │   ├── met_files_with_co2_obs/               $SHADING_MET_FILES_WITH_CO2
    │   └── final_met_files_for_sims/             $SHADING_MET_OUT_DIR
    ├── apsim_templates_before_checking/          $SHADING_APSIM_TEMPLATES_BEFORE_CHECKING_DIR
    ├── apsimx_templates_for_duplication/         $SHADING_APSIMX_TEMPLATES_FOR_DUPLICATION_DIR
    ├── apsim_manifests/                          $SHADING_MANIFEST_DIR
    │   ├── apsimx_files.manifest         [3]     $SHADING_APSIM_MANIFEST
    │   ├── db_files.manifest             [3]     $SHADING_DB_MANIFEST
    │   └── raw_parquet_files.manifest    [3]     $SHADING_RAW_PARQUET_MANIFEST
    ├── apsim_simulations/                        $SHADING_APSIM_SIMULATIONS_DIR
    ├── all_raw_data_parquet_files/               $SHADING_RAW_DATA_PARQUET_DIR
    └── processed_files_for_data_analysis/        $SHADING_PROCESSED_FILES_FOR_ANALYSIS_DIR

[1] TO SET UP APSIM CONTAINER: 
- how to set up apsim container 
_ *need to check that URL is public or move into this directory * 
ALL RAN FROM THE LINUX TERMINAL/COMMAND LINE:
1. cd $APSIM_CONTAINER_DIR
2. curl -o apsim.Singularity https://raw.githubusercontent.com/katemaddern/apsim/refs/heads/main/Singularity.2026.09.8109.0
3. ls -> should see a new file called 'apsim.Singularity' 
4. singularity build --remote $scratch/APSIM-NextGen-process-based-evaluation-shading-experiments/apsim_container/apsim_2026_09_8109_0.sif apsim.Singularity
    - is actually singularity build --remote $APSIM_CONTAINER_DIR/apsim_2026_09_8109_0.sif apsim.Singularity
5. If first time set up or it has been a while: 
    Step 5a: If it has been a while it will prompt about an ‘expired token’ for sys labs. If that is the case, run this from the terminal: singularity remote login
    Step 5b: Then go to: https://cloud.sylabs.io/auth/tokens (login with github). Then head to ‘Access Tokens’, ‘Create New Tokens’, call it something and then copy the token (it’s about 4 lines long and you only get one chance to access it). 
    Step 5c: Paste this token into the terminal and it should accept it. Then rerun the command from step 4 – this might take a while and if it works the final line will say ‘INFO:    Image uploaded successfully.’ 
6. After running step 4, it should build the container - you'll see a lot of lines of Unpacking, Selecting, Preparing, Setting up, Installing, Certificate added and so on. If it has worked, the final line will say ‘INFO:    Image uploaded successfully.’ and then eventually the job will end on the command line 

Full credit to James Bristow (https://github.com/JBris) for the code to install APSIM NextGen as a singularity container. Original version that I modified available here: https://github.com/JBris/auto-apsim-singularity/blob/fa59b91b3fce2d1a2d0133727c1355a8a8d323a5/templates/Singularity.template



Papers referenced in code: 
- Celestina growth stage paper 
- Fischer 2024 paper for crit period defs  
- All critical period defs papers