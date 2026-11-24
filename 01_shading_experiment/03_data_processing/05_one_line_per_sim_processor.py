import os
import sys
from pathlib import Path
import datetime
import time
import psutil
import pandas as pd 
import numpy as np
import re

SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg

try:
    print("The script used to generate this output is", os.path.basename(__file__))
    print("The script above can be found in this directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode; __file__ is not defined.")

print("This script started running at:", datetime.datetime.now())

start_time = time.time()

def print_usage(stage):
    process = psutil.Process(os.getpid())
    mem_MB = process.memory_info().rss / 1024 ** 2
    print(f"{stage} - Memory usage: {mem_MB:.2f} MB")

print_usage("Start")

insite=sys.argv[1]
print(f"insite = {insite}")

###########VARIABLES USED THROUGH OUT ###########
# Columns identifying one simulation run
merge_cols = [
    'SITE', 'YEAR', 'VARIABLE', 'SHIFT',
    'PERCENTCHANGE', 'SHIFT_DOY', 'CULTIVAR',
]
# Run identifier + date = one row per day
daily_merge_cols = merge_cols + ['DATE']


###########CONFIG/FILE LOCATIONS###########
INPUT_RAW_PARQUET_DIR = cfg.SHADING_RAW_DATA_PARQUET_DIR
OUTPUT_PROCESSED_FILE_DIR = cfg.SHADING_PROCESSED_FILES_BEFORE_BINDING_DIR

# Input file
INPUT_RAW_PARQUET_FILE = os.path.join(
    INPUT_RAW_PARQUET_DIR,
    f"{insite}.parquet"
)

###########READ IN RAW PARQUET FILE########### 
df = pd.read_parquet(INPUT_RAW_PARQUET_FILE)


##############################################################################################################################################
###################Data formatting ###########################################################################################################
##############################################################################################################################################

###########COLUMN NAME FORMATTING########### 
df.columns = [col.upper() for col in df.columns]
df.columns = df.columns.str.replace('.', '_')
df.rename(columns = {"CLOCK_TODAY" : "DATE"}, inplace = True)

print(df['SIM_FILE'].unique())

RAW_COLS = set(df.columns)

###########EXTRACT EXPERIMENTAL VARIABLES FROM SIM FILE/APSIM FILE NAME###########
PATTERN = re.compile(r'^([^_]+)_(\d{4})_([^_]+)_([^_]+)_([^_]+)_([^_]+)_([^_]+)$')
NEW_COLS = ['SITE', 'YEAR', 'VARIABLE', 'SHIFT', 'PERCENTCHANGE', 'SHIFT_DOY', 'CULTIVAR']

# Extract all parts for every row at once (rows that don't match become NaN)
extracted_strings = df['SIM_FILE'].str.extract(PATTERN)
extracted_strings.columns = NEW_COLS

# Check in case SIM_FILE has broken somewhere
bad = extracted_strings.isna().all(axis=1)
if bad.any():
    for f in df.loc[bad, 'SIM_FILE'].unique():
        print(f"Error: filename doesn't match "
              f"'site_year_variable_shift_percentchange_doy_cultivar.apsimx': {f}")
    raise ValueError(f"{bad.sum()} row(s) have an invalid SIM_FILE name")

# Print to check 
for f, row in extracted_strings.assign(SIM_FILE=df['SIM_FILE']).drop_duplicates('SIM_FILE').iterrows():
    print(f"Processing {row['SIM_FILE']} - site: {row['SITE']}, year: {row['YEAR']}, "
          f"variable: {row['VARIABLE']}, shift: {row['SHIFT']}, "
          f"percentchange: {row['PERCENTCHANGE']}, doy: {row['SHIFT_DOY']}, "
          f"cultivar: {row['CULTIVAR']}")

# Make new cols 
df[NEW_COLS] = extracted_strings

# Make extracted strings into numbers 
for c in ['YEAR', 'SHIFT_DOY', 'PERCENTCHANGE']:
       df[c] = pd.to_numeric(df[c], errors='coerce')

###########DEALING_WITH_DATES###########
#Need to not overwrite the good YEAR value from above 
# Make sure DATE is datetime once, up front
df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')

# Now pull components
df['YEAR_DATE'] = df['DATE'].dt.year
# df['MONTH'] = df['DATE'].dt.month
# df['DAY_OF_MONTH'] = df['DATE'].dt.day
df['DOY'] = df['DATE'].dt.dayofyear

#Now get DOY to run into next year 
#If the current year ('YEAR_DATE' from the current day of the simulation) is not the year that the experiment started in ('YEAR' from the sim file), ... 
# ... add 365 to DOY and if the year that the experiment started in was a leap year, add 1 for the extra day
# ... if still in the year the experiment started in, DOY is just copied over
df['DOY_CONT'] = np.where(
    df['YEAR_DATE'] > df['YEAR'],
    df['DOY'] + 365 + pd.to_datetime(df['YEAR'].astype(str)).dt.is_leap_year,
    df['DOY']
)

##########GETTING SHADING PERIOD DAYS###########
#All functions must be inclusive e.g. these days are being shaded as well
df['START_SHADING_DOY'] = df['SHIFT_DOY'] - 7
df['END_SHADING_DOY'] = df['SHIFT_DOY'] + 6
df['MID_SHADING_DOY'] = df['SHIFT_DOY'] # To keep things consistent/easy to read when plotting 

##############################################################################################################################################
################### DEGREE DAY CALCUATIONS FOR COMPARISION WITH FISCHER ######################################################################
##############################################################################################################################################

df['DEGREE_DAY'] = (df['WEATHER_MAXT'] + df['WEATHER_MINT']) / 2 

df['DEGREE_DAY_45'] = ((df['WEATHER_MAXT'] + df['WEATHER_MINT']) / 2) - 4.5

##Calculating cumulative degree days only while the crop is growing 
#Filter to only when the crop is growing 
df_growing = df[
    df['WHEAT_PHENOLOGY_CURRENTPHASENAME'].notna() &
    (df['WHEAT_PHENOLOGY_CURRENTPHASENAME'] != "")
].sort_values('DATE').copy()

df_growing['WHEAT_SOWINGDATE'] = pd.to_datetime(df_growing['WHEAT_SOWINGDATE'], errors='coerce')
df_growing['TOS_DOY'] = df_growing['WHEAT_SOWINGDATE'].dt.dayofyear

df_growing['CUM_DEGREE_DAY']    = df_growing['DEGREE_DAY'].cumsum()
df_growing['CUM_DEGREE_DAY_45'] = df_growing['DEGREE_DAY_45'].cumsum()

DIFF_COLS = [
    'WHEAT_GRAIN_WT',
    'WHEAT_STEMPLUSSPIKE_WT',
    'WHEATABOVEGROUNDWTKGHA',
    'WHEAT_STEM_WT',
    'WHEAT_SPIKE_WT',
    'WHEAT_ROOT_WT',
    'WHEAT_LEAF_WT',
    'WHEAT_PHENOLOGY_ACCUMULATEDTT',
    'WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT',
]

diff_cols_present = [c for c in DIFF_COLS if c in df_growing.columns]
diffs = df_growing[diff_cols_present].diff()
diffs.columns = [f'DAILY_CHANGE_{c}' for c in diff_cols_present]
df_growing = pd.concat([df_growing, diffs], axis=1)

keep_cols = daily_merge_cols + ['TOS_DOY', 'WHEAT_SOWINGDATE', 'CUM_DEGREE_DAY', 'CUM_DEGREE_DAY_45'] + list(diffs.columns)
df = df.merge(df_growing[keep_cols], on=daily_merge_cols, how='left')
del diffs


##############################################################################################################################################
################### Getting variables at all Aus. Phen. Stages (Celestina et al 2023) ########################################################
##############################################################################################################################################

# Output cumulative normal degree days, and normal degree days minus 4.5 for each growth stage 

ALL_STAGES = [
    ('Germination',              'GERMINATION'),
    ('Emergence',                'EMERGENCE'),
    ('DoubleRidge',              'DOUBLE_RIDGE'),
    ('MaximumSpikeletPrimordia', 'MAX_SPIKELET_PRIMORDIA'),
    ('FlagLeafAppearance',       'FLAG_LEAF'),
    ('HeadEmergence',            'HEAD_EMERGENCE'),
    ('Anthesis',                 'ANTHESIS_STAGE'),
    ('MaximumGrainLength',       'MAX_GRAIN_LENGTH'),
    ('EndGrainFill',             'END_GRAIN_FILL'),
    ('HarvestRipe',              'MATURITY'),
]

# source column -> output base name (stage prefix gets appended)
SNAP_COLS = {
    'DOY':                                  'DOY',
    'DOY_CONT':                             'DOY_CONT',
    'DATE':                                 'DATE',
    'WHEAT_PHENOLOGY_ACCUMULATEDTT':        'ACCUMULATEDTT_APSIM_DD',
    'WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT': 'ACCUMULATEDEMERGEDTT_APSIM_DD',
    'WHEAT_PHENOLOGY_ZADOK_STAGE':           'ZADOK_STAGE',
    'WHEAT_PHENOLOGY_STAGE':                  'STAGE', #This is a duplicate of the stage names, but needed for the shading period outputs
    'WHEATABOVEGROUNDWTKGHA':               'BIOMASS_KGHA',
    'WHEAT_LAI':                            'LAI',
    'WHEAT_GRAIN_SIZE':                     'GRAIN_SIZE',
    'WHEAT_GRAIN_NUMBER':                   'GRAIN_NUMBER',
    'WHEAT_GRAIN_TOTAL_WT':                 'GRAIN_WEIGHT',
    'WHEAT_SPIKE_WT':                       'SPIKE_WEIGHT',
    'WHEAT_STEM_WT':                        'STEM_WEIGHT',
    'WHEAT_STEMPLUSSPIKE_STORAGEWT':        'STEM_AND_SPIKE_STORAGE_WEIGHT',
    'WHEAT_STEMPLUSSPIKE_STRUCTURALWT':     'STEM_AND_SPIKE_STRUCTURAL_WEIGHT',
    'WHEAT_STEMPLUSSPIKE_WT':               'STEM_AND_SPIKE_WEIGHT',
    'CUM_DEGREE_DAY':                       'CUM_DEGREE_DAY', 
    'CUM_DEGREE_DAY_45':                    'CUM_DEGREE_DAY_45', 
    'YIELD':                                'YIELD', 
    'WHEAT_LEAF_COVERGREEN':                'COVERGREEN', 
}

#Set column to find stages in 
stage_col = df['WHEAT_PHENOLOGY_CURRENTSTAGENAME']
snap_cols = {c: n for c, n in SNAP_COLS.items() if c in df.columns}

new = {}
for stage_name, prefix in ALL_STAGES:
    row = df.loc[stage_col == stage_name, list(snap_cols)]
    if row.empty:
        print(f"  Note: no rows for stage '{stage_name}' – skipping.")
        continue
    for col, name in snap_cols.items():
        new[f'{name}_{prefix}'] = row[col].iloc[0]

df = pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1)

##############################################################################################################################################
################### Calculations over whole growing period #########################################################################################
##############################################################################################################################################

df_growing_merge = df_growing.groupby(merge_cols, as_index=False, dropna=False).agg(
        N_DAYS_CROP_ALIVE_IN_CROP_GROWING=('DATE', 'count'),
        #Radiation incoming
        MEAN_RADIATION_INCOMING_CROP_GROWING=('WEATHER_RADN', 'mean'),
        SUM_RADIATION_INCOMING_CROP_GROWING= ('WEATHER_RADN', 'sum'),
        #Radiation intercepted
        MEAN_RADIATION_INTERCEPTED_CROP_GROWING=('WHEAT_LEAF_RADIATIONINTERCEPTED', 'mean'),
        SUM_RADIATION_INTERCEPTED_CROP_GROWING= ('WHEAT_LEAF_RADIATIONINTERCEPTED', 'sum'),
        #RUE
        MEAN_RUE_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'mean'),
        SUM_RUE_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'sum'),
        #Stress vars
        MEAN_N_STRESS_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'mean'),
        SUM_N_STRESS_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'sum'),
        MEAN_TEMP_STRESS_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'mean'),
        SUM_TEMP_STRESS_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'sum'),
        MEAN_WATER_STRESS_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'mean'),
        SUM_WATER_STRESS_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'sum'),
        MEAN_VPD_STRESS_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'mean'),
        SUM_VPD_STRESS_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'sum'),
        MEAN_CO2_STRESS_CROP_GROWING=('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'mean'),
        SUM_CO2_STRESS_CROP_GROWING= ('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'sum'),
        #Degree days 
        MEAN_DEGREE_DAY_CROP_GROWING=('DEGREE_DAY', 'mean'),
        SUM_DEGREE_DAY_CROP_GROWING= ('DEGREE_DAY', 'sum'),
        MEAN_DEGREE_DAY_45_CROP_GROWING=('DEGREE_DAY_45', 'mean'),
        SUM_DEGREE_DAY_45_CROP_GROWING= ('DEGREE_DAY_45', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_CROP_GROWING=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_CROP_GROWING=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDTT_CROP_GROWING=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDTT_CROP_GROWING=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'sum'),
        #Changes in biomass
        MEAN_DAILY_BIOMASS_CHANGE_CROP_GROWING=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'mean'),
        SUM_DAILY_BIOMASS_CHANGE_CROP_GROWING=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'sum'),
        #Changes in spike weight 
        MEAN_DAILY_SPIKE_WEIGHT_CHANGE_CROP_GROWING=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'mean'),
        SUM_DAILY_SPIKE_WEIGHT_CROP_GROWING=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'sum'),
)

# Merge back into original dataframe
df = df.merge(df_growing_merge, on=merge_cols, how='left')  


##############################################################################################################################################
################### Report above variables on shading period days #########################################################################################
################### At 'START_SHADING_DOY', 'MID_SHADING_DOY', 'END_SHADING_DOY' ##################################################################
##############################################################################################################################################

SHADING_EVENTS = [
    ('START_SHADING_DOY', 'START_SHADING'),
    ('MID_SHADING_DOY',   'MID_SHADING'),
    ('END_SHADING_DOY',   'END_SHADING'),
]

snap_cols = {c: n for c, n in SNAP_COLS.items() if c in df.columns}

new = {}
for event_col, prefix in SHADING_EVENTS:
    if event_col not in df.columns:
        print(f"  Note: column '{event_col}' not found – skipping.")
        continue
    row = df.loc[df['DOY_CONT'] == df[event_col], list(snap_cols)]
    if row.empty:
        print(f"  Note: no rows where DOY_CONT == {event_col} – skipping.")
        continue
    for col, name in snap_cols.items():
        new[f'{name}_{prefix}'] = row[col].iloc[0]

df = pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1)

##############################################################################################################################################
################### Calculations over shading period #########################################################################################
################### From 'START_SHADING_DOY' to 'END_SHADING_DOY' inclusive ##################################################################
##############################################################################################################################################

# Select the days that are being shaded while the crop is alive, inclusive to match setup 
df_within_shading_period = df_growing[
    (df_growing['DOY_CONT'] >= df_growing['START_SHADING_DOY']) &
    (df_growing['DOY_CONT'] <= df_growing['END_SHADING_DOY'])
]

df_within_shading_period = df_within_shading_period.groupby(merge_cols, as_index=False, dropna=False).agg(
        N_DAYS_CROP_ALIVE_IN_SHADING_PERIOD=('DATE', 'count'),
        #Radiation incoming
        MEAN_RADIATION_INCOMING_SHADING_PERIOD=('WEATHER_RADN', 'mean'),
        SUM_RADIATION_INCOMING_SHADING_PERIOD= ('WEATHER_RADN', 'sum'),
        #Radiation intercepted
        MEAN_RADIATION_INTERCEPTED_SHADING_PERIOD=('WHEAT_LEAF_RADIATIONINTERCEPTED', 'mean'),
        SUM_RADIATION_INTERCEPTED_SHADING_PERIOD= ('WHEAT_LEAF_RADIATIONINTERCEPTED', 'sum'),
        #RUE
        MEAN_RUE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'mean'),
        SUM_RUE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'sum'),
        #Stress vars
        MEAN_N_STRESS_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'mean'),
        SUM_N_STRESS_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'sum'),
        MEAN_TEMP_STRESS_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'mean'),
        SUM_TEMP_STRESS_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'sum'),
        MEAN_WATER_STRESS_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'mean'),
        SUM_WATER_STRESS_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'sum'),
        MEAN_VPD_STRESS_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'mean'),
        SUM_VPD_STRESS_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'sum'),
        MEAN_CO2_STRESS_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'mean'),
        SUM_CO2_STRESS_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'sum'),
        #Degree days 
        MEAN_DEGREE_DAY_SHADING_PERIOD=('DEGREE_DAY', 'mean'),
        SUM_DEGREE_DAY_SHADING_PERIOD= ('DEGREE_DAY', 'sum'),
        MEAN_DEGREE_DAY_45_SHADING_PERIOD=('DEGREE_DAY_45', 'mean'),
        SUM_DEGREE_DAY_45_SHADING_PERIOD= ('DEGREE_DAY_45', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDTT_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDTT_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'sum'),
        #Changes in biomass
        MEAN_DAILY_BIOMASS_CHANGE_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'mean'),
        SUM_DAILY_BIOMASS_CHANGE_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'sum'),
        #Changes in spike weight 
        MEAN_DAILY_SPIKE_WEIGHT_CHANGE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'mean'),
        SUM_DAILY_SPIKE_WEIGHT_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'sum'),
)

# Merge back into original dataframe
df = df.merge(df_within_shading_period, on=merge_cols, how='left')  

##############################################################################################################################################
################### Calculations BEFORE shading period #########################################################################################
################### All days before shading starts ##################################################################
##############################################################################################################################################

# Select the days that are being shaded while the crop is alive, inclusive to match setup 
df_before_shading_period = df_growing[
    (df_growing['DOY_CONT'] < df_growing['START_SHADING_DOY'])
]

df_before_shading_period = df_before_shading_period.groupby(merge_cols, as_index=False, dropna=False).agg(
        N_DAYS_CROP_ALIVE_IN_PRE_SHADING_PERIOD=('DATE', 'count'),
        #Radiation incoming
        MEAN_RADIATION_INCOMING_PRE_SHADING_PERIOD=('WEATHER_RADN', 'mean'),
        SUM_RADIATION_INCOMING_PRE_SHADING_PERIOD= ('WEATHER_RADN', 'sum'),
        #Radiation intercepted
        MEAN_RADIATION_INTERCEPTED_PRE_SHADING_PERIOD=('WHEAT_LEAF_RADIATIONINTERCEPTED', 'mean'),
        SUM_RADIATION_INTERCEPTED_PRE_SHADING_PERIOD= ('WHEAT_LEAF_RADIATIONINTERCEPTED', 'sum'),
        #RUE
        MEAN_RUE_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'mean'),
        SUM_RUE_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'sum'),
        #Stress vars
        MEAN_N_STRESS_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'mean'),
        SUM_N_STRESS_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'sum'),
        MEAN_TEMP_STRESS_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'mean'),
        SUM_TEMP_STRESS_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'sum'),
        MEAN_WATER_STRESS_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'mean'),
        SUM_WATER_STRESS_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'sum'),
        MEAN_VPD_STRESS_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'mean'),
        SUM_VPD_STRESS_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'sum'),
        MEAN_CO2_STRESS_PRE_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'mean'),
        SUM_CO2_STRESS_PRE_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'sum'),
        #Degree days 
        MEAN_DEGREE_DAY_PRE_SHADING_PERIOD=('DEGREE_DAY', 'mean'),
        SUM_DEGREE_DAY_PRE_SHADING_PERIOD= ('DEGREE_DAY', 'sum'),
        MEAN_DEGREE_DAY_45_PRE_SHADING_PERIOD=('DEGREE_DAY_45', 'mean'),
        SUM_DEGREE_DAY_45_PRE_SHADING_PERIOD= ('DEGREE_DAY_45', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDTT_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDTT_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'sum'),
        #Changes in biomass
        MEAN_DAILY_BIOMASS_CHANGE_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'mean'),
        SUM_DAILY_BIOMASS_CHANGE_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'sum'),
        #Changes in spike weight 
        MEAN_DAILY_SPIKE_WEIGHT_CHANGE_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'mean'),
        SUM_DAILY_SPIKE_WEIGHT_PRE_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'sum'),
)

# Merge back into original dataframe
df = df.merge(df_before_shading_period, on=merge_cols, how='left')  

##############################################################################################################################################
################### Calculations AFTER shading period #########################################################################################
################### All days before shading starts ##################################################################
##############################################################################################################################################

# Select the days that are being shaded while the crop is alive, inclusive to match setup 
df_after_shading_period = df_growing[
    (df_growing['DOY_CONT'] > df_growing['END_SHADING_DOY'])
]

df_after_shading_period = df_after_shading_period.groupby(merge_cols, as_index=False, dropna=False).agg(
        N_DAYS_CROP_ALIVE_IN_POST_SHADING_PERIOD=('DATE', 'count'),
        #Radiation incoming
        MEAN_RADIATION_INCOMING_POST_SHADING_PERIOD=('WEATHER_RADN', 'mean'),
        SUM_RADIATION_INCOMING_POST_SHADING_PERIOD= ('WEATHER_RADN', 'sum'),
        #Radiation intercepted
        MEAN_RADIATION_INTERCEPTED_POST_SHADING_PERIOD=('WHEAT_LEAF_RADIATIONINTERCEPTED', 'mean'),
        SUM_RADIATION_INTERCEPTED_POST_SHADING_PERIOD= ('WHEAT_LEAF_RADIATIONINTERCEPTED', 'sum'),
        #RUE
        MEAN_RUE_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'mean'),
        SUM_RUE_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'sum'),
        #Stress vars
        MEAN_N_STRESS_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'mean'),
        SUM_N_STRESS_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'sum'),
        MEAN_TEMP_STRESS_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'mean'),
        SUM_TEMP_STRESS_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'sum'),
        MEAN_WATER_STRESS_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'mean'),
        SUM_WATER_STRESS_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'sum'),
        MEAN_VPD_STRESS_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'mean'),
        SUM_VPD_STRESS_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'sum'),
        MEAN_CO2_STRESS_POST_SHADING_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'mean'),
        SUM_CO2_STRESS_POST_SHADING_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'sum'),
        #Degree days 
        MEAN_DEGREE_DAY_POST_SHADING_PERIOD=('DEGREE_DAY', 'mean'),
        SUM_DEGREE_DAY_POST_SHADING_PERIOD= ('DEGREE_DAY', 'sum'),
        MEAN_DEGREE_DAY_45_POST_SHADING_PERIOD=('DEGREE_DAY_45', 'mean'),
        SUM_DEGREE_DAY_45_POST_SHADING_PERIOD= ('DEGREE_DAY_45', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDTT_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDTT_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'sum'),
        #Changes in biomass
        MEAN_DAILY_BIOMASS_CHANGE_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'mean'),
        SUM_DAILY_BIOMASS_CHANGE_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'sum'),
        #Changes in spike weight 
        MEAN_DAILY_SPIKE_WEIGHT_CHANGE_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'mean'),
        SUM_DAILY_SPIKE_WEIGHT_POST_SHADING_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'sum'),
)

# Merge back into original dataframe
df = df.merge(df_after_shading_period, on=merge_cols, how='left')  

##############################################################################################################################################
################### Calculations over critical period ########################################################################################
################### Fischer 2024 def: Flag leaf -> Anthesis inclusive ########################################################################
##############################################################################################################################################

# Select the days that in the critical period, inclusive of day of stage 
df_within_critical_period = df[df['DOY_CONT'] >= df['DOY_CONT_FLAG_LEAF']]
df_within_critical_period = df_within_critical_period[df_within_critical_period['DOY_CONT'] <= df_within_critical_period['DOY_CONT_ANTHESIS_STAGE']]

df_within_critical_period = df_within_critical_period.groupby(merge_cols, as_index=False, dropna=False).agg(
        #Radiation incoming
        MEAN_RADIATION_INCOMING_CRITICAL_PERIOD=('WEATHER_RADN', 'mean'),
        SUM_RADIATION_INCOMING_CRITICAL_PERIOD= ('WEATHER_RADN', 'sum'),
        #Radiation intercepted
        MEAN_RADIATION_INTERCEPTED_CRITICAL_PERIOD=('WHEAT_LEAF_RADIATIONINTERCEPTED', 'mean'),
        SUM_RADIATION_INTERCEPTED_CRITICAL_PERIOD= ('WHEAT_LEAF_RADIATIONINTERCEPTED', 'sum'),
        #RUE
        MEAN_RUE_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'mean'),
        SUM_RUE_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT', 'sum'),
        #Stress vars
        MEAN_N_STRESS_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'mean'),
        SUM_N_STRESS_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'sum'),
        MEAN_TEMP_STRESS_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'mean'),
        SUM_TEMP_STRESS_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FT', 'sum'),
        MEAN_WATER_STRESS_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'mean'),
        SUM_WATER_STRESS_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'sum'),
        MEAN_VPD_STRESS_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'mean'),
        SUM_VPD_STRESS_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FVPD', 'sum'),
        MEAN_CO2_STRESS_CRITICAL_PERIOD=('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'mean'),
        SUM_CO2_STRESS_CRITICAL_PERIOD= ('WHEAT_LEAF_PHOTOSYNTHESIS_FCO2', 'sum'),
        #Degree days 
        MEAN_DEGREE_DAY_CRITICAL_PERIOD=('DEGREE_DAY', 'mean'),
        SUM_DEGREE_DAY_CRITICAL_PERIOD= ('DEGREE_DAY', 'sum'),
        MEAN_DEGREE_DAY_45_CRITICAL_PERIOD=('DEGREE_DAY_45', 'mean'),
        SUM_DEGREE_DAY_45_CRITICAL_PERIOD= ('DEGREE_DAY_45', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDEMERGEDTT_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT', 'sum'),
        MEAN_DEGREE_DAY_APSIM_ACCUMULATEDTT_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'mean'),
        SUM_DEGREE_DAY_APSIM_ACCUMULATEDTT_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_PHENOLOGY_ACCUMULATEDTT', 'sum'),
        #Changes in biomass
        MEAN_DAILY_BIOMASS_CHANGE_CRITICAL_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'mean'),
        SUM_DAILY_BIOMASS_CHANGE_CRITICAL_PERIOD=('DAILY_CHANGE_WHEATABOVEGROUNDWTKGHA', 'sum'),
        #Changes in spike weight 
        MEAN_DAILY_SPIKE_WEIGHT_CHANGE_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'mean'),
        SUM_DAILY_SPIKE_WEIGHT_CRITICAL_PERIOD=('DAILY_CHANGE_WHEAT_SPIKE_WT', 'sum'),
)

# Merge back into original dataframe
df = df.merge(df_within_critical_period, on=merge_cols, how='left')  

################Calculate Fischer Terms#####################
df['DURATION_CRITICAL_PERIOD'] = df['DOY_CONT_ANTHESIS_STAGE'] - df['DOY_CONT_FLAG_LEAF']

df['BIOMASS_FLAG_LEAF_GRAMS_M2'] = df['BIOMASS_KGHA_FLAG_LEAF'] / 10
df['BIOMASS_ANTHESIS_GRAMS_M2']   = df['BIOMASS_KGHA_ANTHESIS_STAGE']   / 10

df['CROP_GROWTH_RATE_CRITICAL_PERIOD'] = (
    (df['BIOMASS_ANTHESIS_GRAMS_M2'] - df['BIOMASS_FLAG_LEAF_GRAMS_M2'])
    / df['DURATION_CRITICAL_PERIOD']
)
df['PARTITIONING_TO_SPIKE_CRITICAL_PERIOD'] = (
    (df['SPIKE_WEIGHT_ANTHESIS_STAGE'] - df['SPIKE_WEIGHT_FLAG_LEAF'])
    / (df['BIOMASS_ANTHESIS_GRAMS_M2'] - df['BIOMASS_FLAG_LEAF_GRAMS_M2'])
)

df['FRUITING_EFFICIENCY_CRITICAL_PERIOD'] = (
    df['GRAIN_NUMBER_MATURITY'] / df['SPIKE_WEIGHT_ANTHESIS_STAGE']
)


##############################################################################################################################################
################### Getting other critical period definition start and end days ##############################################################
##############################################################################################################################################

# Rows must be in date order so "first day" and "last day" mean earliest and latest
df = df.sort_values('DATE').reset_index(drop=True)

###########HELPER FUNCTIONS###########

def first_day(mask):
    """Return the earliest row of df where mask is True, or None if there isn't one."""
    days = df[mask]
    return None if days.empty else days.iloc[0]

def last_day(mask):
    """Return the latest row of df where mask is True, or None if there isn't one."""
    days = df[mask]
    return None if days.empty else days.iloc[-1]

def day_on(date):
    """Return the row of df for a specific date, or None if that date isn't in the simulation."""
    return first_day(df['DATE'] == date)

# Columns to report on the start and end day of every critical period
# source column -> output base name
PERIOD_SNAP_COLS = {
    'DOY':                                  'DOY',
    'DOY_CONT':                             'DOY_CONT',
    'CUM_DEGREE_DAY':                       'CUM_DEGREE_DAY',
    'CUM_DEGREE_DAY_45':                    'CUM_DEGREE_DAY_45',
    'WHEAT_PHENOLOGY_ACCUMULATEDEMERGEDTT': 'ACCUMULATEDEMERGEDTT_APSIM_DD',
}

def record_period(name, start_day, end_day):
    """
    Save the start and end of a critical period as columns on every row, e.g.
    DOY_START_SADRAS_2022_CRIT_PERIOD, CUM_DEGREE_DAY_45_START_SADRAS_2022_CRIT_PERIOD,
    DOY_END_SADRAS_2022_CRIT_PERIOD,   CUM_DEGREE_DAY_45_END_SADRAS_2022_CRIT_PERIOD
    """
    for label, day in [('START', start_day), ('END', end_day)]:
        if day is None:
            print(f"  Note: no {label.lower()} day found for {name} critical period.")
        for col, out_name in PERIOD_SNAP_COLS.items():
            value = np.nan if (day is None or col not in day.index) else day[col]
            df[f'{out_name}_{label}_{name}_CRIT_PERIOD'] = value

###########THERMAL-TIME DEFINITIONS###########
# Critical period = days whose cumulative thermal time lies within
# [value at anthesis - before, value at anthesis + after]

THERMAL_PERIODS = [
    # name,          cumulative column,               value at anthesis,                        before, after
    # Fischer (1985): 300 °Cd before anthesis, base 4.5 °C
    ('FISCHER_1985', 'CUM_DEGREE_DAY_45',             'CUM_DEGREE_DAY_45_ANTHESIS_STAGE',       300,    0),
    # Sadras et al. (2022): 300 °Cd before to 100 °Cd after anthesis, base 4.5 °C
    ('SADRAS_2022',  'CUM_DEGREE_DAY_45',             'CUM_DEGREE_DAY_45_ANTHESIS_STAGE',       300,    100),
    # Extra definitions (not in manuscript) – same window, different thermal time to understand impact of calculations
    ('APSIM',        'WHEAT_PHENOLOGY_ACCUMULATEDTT', 'ACCUMULATEDTT_APSIM_DD_ANTHESIS_STAGE',  300,    100),
    ('TEMP',         'CUM_DEGREE_DAY',                'CUM_DEGREE_DAY_ANTHESIS_STAGE',          300,    100),
]

for name, cum_col, anthesis_col, before, after in THERMAL_PERIODS:
    if anthesis_col not in df.columns:
        print(f"  Note: '{anthesis_col}' not found (anthesis not reached?) – skipping {name}.")
        continue
    anthesis_value = df[anthesis_col].iloc[0]
    in_window = (df[cum_col] >= anthesis_value - before) & (df[cum_col] <= anthesis_value + after)
    record_period(name, first_day(in_window), last_day(in_window))

###########CALENDAR-DAY DEFINITIONS###########
# Fixed numbers of days before/after the anthesis date

if 'DATE_ANTHESIS_STAGE' in df.columns:
    anthesis_date = pd.to_datetime(df['DATE_ANTHESIS_STAGE'].iloc[0])
    seven_days_after_anthesis = day_on(anthesis_date + pd.Timedelta(days=7))

    # Slafer et al. (2021): 21 days before to 7 days after anthesis
    record_period('SLAFER_2021',
                  day_on(anthesis_date - pd.Timedelta(days=21)),
                  seven_days_after_anthesis)

    # Porker et al. (2025): 20 days before to 10 days after anthesis
    record_period('PORKER_2025',
                  day_on(anthesis_date - pd.Timedelta(days=20)),
                  day_on(anthesis_date + pd.Timedelta(days=10)))

    # Slafer et al. (2023): onset of stem elongation to 7 days after anthesis
    record_period('SLAFER_2023',
                  first_day(df['WHEAT_PHENOLOGY_CURRENTPHASENAME'] == 'StemElongating'),
                  seven_days_after_anthesis)
else:
    print("  Note: 'DATE_ANTHESIS_STAGE' not found – skipping SLAFER_2021, PORKER_2025 and SLAFER_2023.")

###########PHENOLOGICAL-STAGE DEFINITIONS###########

stage = df['WHEAT_PHENOLOGY_CURRENTSTAGENAME']
zadok = df['WHEAT_PHENOLOGY_ZADOK_STAGE']

# Fischer et al. (2024): flag leaf appearance to anthesis
record_period('FISCHER_2024',
              first_day(stage == 'FlagLeafAppearance'),
              first_day(stage == 'Anthesis'))

# Dreccer et al. (2000): Zadok 39 (flag leaf ligule just visible) to Zadok 71 (end of anthesis in her words)
# ">=" catches the first day at or past each stage, even if APSIM's Zadok value skips a whole number
record_period('DRECCER_2000',
              first_day(zadok >= 39),
              first_day(zadok >= 71))

###########SPIKE-WEIGHT DEFINITION###########

# Abbate et al. (1997): 5% of maximum spike weight to maximum spike weight
spike = df['WHEAT_SPIKE_WT']
max_spike = spike.max()
if pd.notna(max_spike) and max_spike > 0:
    record_period('ABBATE_1997',
                  first_day(spike >= 0.05 * max_spike),
                  first_day(spike == max_spike))
else:
    print("  Note: no spike weight data – skipping ABBATE_1997.")


##############################################################################################################################################
################### Export and save 1 row file  ##############################################################################################
##############################################################################################################################################

#Filtering to 1 row, making the script stop if 0 or more than 1 present 
df_full = df[df['WHEAT_PHENOLOGY_CURRENTSTAGENAME'] == 'HarvestRipe'].copy()

# Stop if the crop never reached harvest ripe (e.g. failed crop or simulation ended early)
if df_full.empty:
    raise ValueError(
        f"{insite}: no 'HarvestRipe' row found – crop did not reach maturity. "
        f"Last stage reached: {df['WHEAT_PHENOLOGY_CURRENTSTAGENAME'].dropna().iloc[-1] if df['WHEAT_PHENOLOGY_CURRENTSTAGENAME'].notna().any() else 'none'}"
    )

# Stop if there is more than one harvest-ripe row (should be exactly one per simulation)
if len(df_full) > 1:
    raise ValueError(f"{insite}: expected 1 'HarvestRipe' row, found {len(df_full)}")

#Dropping all unused columns from the simulations 
###########KEEP ONLY COLUMNS USED OR CREATED IN THIS SCRIPT###########
# Raw APSIM columns this script reads (anything created by the script is kept automatically)
RAW_COLS_USED = set(
    ['SIM_FILE', 'DATE',
     'WEATHER_MAXT', 'WEATHER_MINT', 'WEATHER_RADN',
     'WHEAT_PHENOLOGY_CURRENTPHASENAME', 'WHEAT_PHENOLOGY_CURRENTSTAGENAME',
     'WHEAT_LEAF_RADIATIONINTERCEPTED', 'WHEAT_LEAF_PHOTOSYNTHESIS_RUEACT',
     'WHEAT_LEAF_PHOTOSYNTHESIS_FN', 'WHEAT_LEAF_PHOTOSYNTHESIS_FT',
     'WHEAT_LEAF_PHOTOSYNTHESIS_FW', 'WHEAT_LEAF_PHOTOSYNTHESIS_FVPD']
    + DIFF_COLS
    + list(SNAP_COLS)   # includes ZADOK, SPIKE_WT, GRAIN_NUMBER etc.
)

keep_cols_final = [c for c in df_full.columns
                   if c not in RAW_COLS or c in RAW_COLS_USED]
dropped = [c for c in df_full.columns if c not in keep_cols_final]

print(f"Keeping {len(keep_cols_final)} columns, dropping {len(dropped)} unused raw columns:")
print(dropped)

df_full = df_full[keep_cols_final]

print('COLUMN NAMES IN DF_FULL')
for col in df_full.columns:
    print(f"'{col}',")

#Saving output parquet file 
out_full = os.path.join(OUTPUT_PROCESSED_FILE_DIR, f"{insite}_full.parquet")
df_full.to_parquet(out_full, index=False)
print(f"Saved _full.parquet: {df_full.shape}  →  {out_full}")


print('finished :)')