#Import packages
import pandas as pd
import polars as pl 
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import time
import psutil
import datetime
import sys
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from matplotlib.ticker import MultipleLocator
import matplotlib.ticker as ticker
import inspect
import matplotlib.lines as mlines
import numpy as np
import matplotlib.ticker as ticker
from pathlib import Path

#Script path and memory usage
try:
    print("The script used to generate this output is", os.path.basename(__file__))
    print("The script above can be found in this directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode; __file__ is not defined.")

print("This script started running at:", datetime.datetime.now())

# --- Timing ---
start_time = time.time()

# --- Memory Usage ---
def print_usage(stage):
    process = psutil.Process(os.getpid())
    mem_MB = process.memory_info().rss / 1024 ** 2
    print(f"{stage} - Memory usage: {mem_MB:.2f} MB")

print_usage("Start")

def add_script_location(script_path, x=0.01, y=0.01, fontsize=6):
    """Add script path, line number, and timestamp to the current figure"""
    caller_line = inspect.currentframe().f_back.f_lineno
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = f"{script_path} (Line {caller_line}) — {timestamp}"
    plt.gcf().text(
        x, y,
        label,
        fontsize=fontsize,
        ha='left',
        va='bottom'
    )

try:
    script_path = os.path.abspath(sys.argv[0])  # Full path
    # script_name = os.path.basename(sys.argv[0])  # Just the file name if preferred
except:
    script_path = "interactive_session"
print(f"Script path: {script_path}")

### Setting location to find config_loader.py and paper_1_functions.py
try:
    SCRIPTS_BASE = Path(__file__).resolve().parents[1]
    print("__file__ was defined")
except NameError:
    print("__file__ not defined (likely Jupyter) — using hardcoded fallback")
    SCRIPTS_BASE = Path("$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments")

# Add scripts directory to Python's module search path
if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))

print(f"Scripts directory: {SCRIPTS_BASE}")

from config_loader import cfg
import paper_1_functions as pf

#Set output directory
os.chdir(cfg.SECOND_DRAFT_DIR)
print(f"Current working directory: {os.getcwd()}")

##DATA LOCATIONS
# Fischer (1985) digitised data and weather: stored with the scripts
DATA_DIR = Path(cfg.ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR)
print(f"Fischer data: {DATA_DIR}")

# APSIM results: the full file if it exists, otherwise the limited file for upload
APSIM_FILE_FULL = Path(cfg.ALL_DATA_SHADED_DF)
APSIM_FILE_LIMITED = Path(cfg.LIMITED_SHADED_DF)
if APSIM_FILE_FULL.is_file():
    APSIM_FILE = APSIM_FILE_FULL
    print(f"APSIM data: full file {APSIM_FILE}")
elif APSIM_FILE_LIMITED.is_file():
    APSIM_FILE = APSIM_FILE_LIMITED
    print(f"APSIM data: full file not found, using the limited file {APSIM_FILE}")
else:
    raise FileNotFoundError(f"No APSIM data file found:\n  {APSIM_FILE_FULL}\n  {APSIM_FILE_LIMITED}")

##IMPORT DATA
#Data from digitsed Figure 1 from Fischer 1985
#Data from https://plotdigitizer.com/app
df_grain_number = pd.read_csv(DATA_DIR / "fischer_grain_number_data.csv")
#df_anthesis_das = pd.read_csv(DATA_DIR / "fischer_50_percent_anthesis_data.csv")
#Use 86 days after sowing reported in Fischer 1975 page 610
df_radiation_data = pd.read_csv(DATA_DIR / "fischer_radiation_data.csv")

df_trend_line = pd.read_csv(DATA_DIR / "fischer_grain_number_trend_line_data.csv")

#Weather file constructed from mean temperature and radiation constructed from mean data presented in Table 1, Fischer 1975 page 608
#Load CIANO daily data
mexico_file_path = DATA_DIR / "fischer_1985_daily_temp_radiation.csv"
df_fischer_to_merge = pd.read_csv(mexico_file_path)
#print(df_ciano.head)
df_fischer_to_merge['SITE'] = "EXP74A" 

print("done")

##MERGING INTO ONE DATAFRAME
df_grain_number['DAYS_AFTER_SOWING'] = (
    df_grain_number['DAYS_AFTER_SOWING']
    .round(0)
    .astype('int64')
)

#Merge digitised grain number percentage from Figure 1
df_fischer = df_fischer_to_merge.merge(
    df_grain_number,
    left_on='DAS',
    right_on='DAYS_AFTER_SOWING',
    how='left'
)

#Delete to prevent x and y DAYS AFTER SOWING
df_fischer = df_fischer.drop(columns=["DAYS_AFTER_SOWING"])

df_radiation_data['DAYS_AFTER_SOWING'] = (
    df_radiation_data['DAYS_AFTER_SOWING']
    .round(0)
    .astype('int64')
)

#Merge radiation from Figure 1
df_fischer = df_fischer.merge(
    df_radiation_data,
    left_on='DAS',
    right_on='DAYS_AFTER_SOWING',
    how='left'
)

df_fischer.columns
print("done")

##CALCULATING DEGREE DAYS FROM ANTHESIS 
#Get value of ACCUMULATED TEMP from DAS == 86 
df_degree_days_at_anthesis = df_fischer[df_fischer['DAS'] == 86]

value_degree_days_at_anthesis = df_degree_days_at_anthesis['ACCUMULATED_TEMP'].iloc[0]

#Create new column where it is das 86 acc temp minus acc temp
df_fischer['DEGREE_DAYS_FROM_ANTHESIS'] = df_fischer['ACCUMULATED_TEMP'] - value_degree_days_at_anthesis

##IMPORT DATA
#Data from digitsed Figure 1 from Fischer 1985
#Data from https://plotdigitizer.com/app
df_trend_line = pd.read_csv(DATA_DIR / "fischer_grain_number_trend_line_data.csv")

#Weather file constructed from mean temperature and radiation constructed from mean data presented in Table 1, Fischer 1975 page 608
#Load CIANO daily data
mexico_file_path = DATA_DIR / "fischer_1985_daily_temp_radiation.csv"
df_fischer_to_merge = pd.read_csv(mexico_file_path)
#print(df_ciano.head)
df_fischer_to_merge['SITE'] = "EXP74A" 

print("done")

##MERGING INTO ONE DATAFRAME
df_trend_line['DAYS_AFTER_SOWING'] = (
    df_trend_line['DAYS_AFTER_SOWING']
    .round(0)
    .astype('int64')
)

print(df_trend_line['DAYS_AFTER_SOWING'].unique())

df_fischer_trend_line = df_fischer_to_merge.merge(
    df_trend_line,
    left_on="DAS",
    right_on="DAYS_AFTER_SOWING",
    how="left"
)

##CALCULATING DEGREE DAYS FROM ANTHESIS 
#Get value of ACCUMULATED TEMP from DAS == 86 
df_degree_days_at_anthesis = df_fischer_trend_line[df_fischer_trend_line['DAS'] == 86]

value_degree_days_at_anthesis = df_degree_days_at_anthesis['ACCUMULATED_TEMP'].iloc[0]

#Create new column where it is das 86 acc temp minus acc temp
df_fischer_trend_line['DEGREE_DAYS_FROM_ANTHESIS'] = df_fischer_trend_line['ACCUMULATED_TEMP'] - value_degree_days_at_anthesis

SINGLE_CULTIVAR = cfg.EXAMPLE_CULTIVAR
# SINGLE_SITE = cfg.EXAMPLE_SITE
SINGLE_SITE = 'millicent'

radiation_file_path = APSIM_FILE   # set in DATA LOCATIONS above

radiation_whole_lazy_frame = pl.scan_parquet(radiation_file_path)
schema = radiation_whole_lazy_frame.collect_schema()

# Column count
column_count = len(schema)
# Row count (efficient)
row_count = radiation_whole_lazy_frame.select(pl.len()).collect().item()
print(f"Rows: {row_count}")
print(f"Columns: {column_count}")

# column_names = list(schema.keys())
# print(column_names)

# Columns used below (must be in the file)
required_columns = ['SITE', 'YEAR', 'CULTIVAR', 'VARIABLE', 'SHIFT_DOY',
                    'DOY_ANTHESIS_STAGE', 'GRAIN_NUMBER_MATURITY', 'DOY_MATURITY',
                    'CUM_DEGREE_DAY_ANTHESIS_STAGE', 'CUM_DEGREE_DAY_MID_SHADING']
# Columns read only if present (not used below; may be missing from the limited file)
optional_columns = ['SIM_FILE', 'SHIFT', 'PERCENTCHANGE', 'WHEAT_GRAIN_NUMBER']
missing_columns = [c for c in required_columns if c not in schema]
if missing_columns:
    raise KeyError(f"Columns not in {radiation_file_path}: {missing_columns}")

radiation_required_lazy_frame = radiation_whole_lazy_frame.select(
    required_columns + [c for c in optional_columns if c in schema])

df_radiation_polars = radiation_required_lazy_frame.collect()
df_apsim = df_radiation_polars.to_pandas()
print("done")

df_apsim = df_apsim[df_apsim['SITE'] == SINGLE_SITE]
df_apsim = df_apsim[df_apsim['CULTIVAR'] == SINGLE_CULTIVAR]

df_apsim['SITE'] = "APSIMNG" 

df_apsim['SHIFT_DOY'] = pd.to_numeric(df_apsim['SHIFT_DOY'], errors='coerce')

df_apsim = df_apsim[df_apsim['SHIFT_DOY'] <= df_apsim['DOY_MATURITY']]

df_apsim_control = df_apsim[df_apsim['VARIABLE'] == 'control']

df_apsim_control_merge =df_apsim_control[['SITE', 'YEAR', 'GRAIN_NUMBER_MATURITY']].rename(columns={'GRAIN_NUMBER_MATURITY' : 'CONTROL_GRAIN_NUMBER_MATURITY',})

df_apsim = df_apsim.merge(df_apsim_control_merge, on=['SITE', 'YEAR'], how='left')

df_apsim['GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL'] = (df_apsim['GRAIN_NUMBER_MATURITY'] / df_apsim['CONTROL_GRAIN_NUMBER_MATURITY']) * 100

df_apsim['SHIFT_DEGREE_DAYS_FROM_ANTHESIS'] = df_apsim['CUM_DEGREE_DAY_MID_SHADING'] - df_apsim['CUM_DEGREE_DAY_ANTHESIS_STAGE']

from scipy import stats

##########SHIFT DOY STATS############

# Initialize results list
results = []

# Get control group (this stays constant)
x_control = (
    df_apsim[
        (df_apsim['VARIABLE'].str.lower() == 'control') &
        (df_apsim['SHIFT_DOY'] == 0)
    ]['GRAIN_NUMBER_MATURITY']
    .dropna()
    .astype(float)
)

# Get unique SHIFT_DOY values for radiation group
shift_doy_values = df_apsim[
    df_apsim['VARIABLE'].str.lower() == 'radiation'
]['SHIFT_DOY'].unique()
shift_doy_values = sorted([doy for doy in shift_doy_values if not np.isnan(doy)])

print(f"Testing {len(shift_doy_values)} different SHIFT_DOY values...")
print(f"SHIFT_DOY range: {min(shift_doy_values)} to {max(shift_doy_values)}")
print("-" * 60)

alpha = 0.05

for shift_doy in shift_doy_values:
    # Get radiation group for current SHIFT_DOY
    y_radiation = (
        df_apsim[
            (df_apsim['VARIABLE'].str.lower() == 'radiation') &
            (df_apsim['SHIFT_DOY'] == shift_doy)
        ]['GRAIN_NUMBER_MATURITY']
        .dropna()
        .astype(float)
    )
    
    # Check if we have enough observations
    if len(x_control) < 2 or len(y_radiation) < 2:
        results.append({
            'SHIFT_DOY': shift_doy,
            'n_control': len(x_control),
            'n_radiation': len(y_radiation),
            'mean_control': np.nan,
            'mean_radiation': np.nan,
            'mean_diff': np.nan,
            'shapiro_control_W': np.nan,
            'shapiro_control_p': np.nan,
            'control_normal': False,
            'shapiro_radiation_W': np.nan,
            'shapiro_radiation_p': np.nan,
            'radiation_normal': False,
            'bartlett_stat': np.nan,
            'bartlett_p': np.nan,
            'equal_variances': False,
            't_statistic': np.nan,
            't_p_value': np.nan,
            'significant_difference': False,
            'notes': f'Insufficient data: n_control={len(x_control)}, n_radiation={len(y_radiation)}'
        })
        continue
    
    # Calculate basic statistics
    mean_control = np.mean(x_control)
    mean_radiation = np.mean(y_radiation)
    mean_diff = mean_radiation - mean_control
    
    # Test normality assumptions
    shapiro_control_W, shapiro_control_p = stats.shapiro(x_control)
    shapiro_radiation_W, shapiro_radiation_p = stats.shapiro(y_radiation)
    control_normal = shapiro_control_p >= alpha
    radiation_normal = shapiro_radiation_p >= alpha
    
    # Test equal variances
    bartlett_stat, bartlett_p = stats.bartlett(x_control, y_radiation)
    equal_variances = bartlett_p >= alpha
    
    # Perform t-test
    t_statistic, t_p_value = stats.ttest_ind(x_control, y_radiation)
    significant_difference = t_p_value <= alpha
    
    # Store results
    results.append({
        'SHIFT_DOY': shift_doy,
        'n_control': len(x_control),
        'n_radiation': len(y_radiation),
        'mean_control': mean_control,
        'mean_radiation': mean_radiation,
        'mean_diff': mean_diff,
        'shapiro_control_W': shapiro_control_W,
        'shapiro_control_p': shapiro_control_p,
        'control_normal': control_normal,
        'shapiro_radiation_W': shapiro_radiation_W,
        'shapiro_radiation_p': shapiro_radiation_p,
        'radiation_normal': radiation_normal,
        'bartlett_stat': bartlett_stat,
        'bartlett_p': bartlett_p,
        'equal_variances': equal_variances,
        't_statistic': t_statistic,
        't_p_value': t_p_value,
        'significant_difference': significant_difference,
        'notes': ''
    })

# Convert to DataFrame
df_stats_results = pd.DataFrame(results)

# Display summary
print(f"\nSUMMARY:")
print(f"Total SHIFT_DOY values tested: {len(df_stats_results)}")
print(f"Significant differences found: {df_stats_results['significant_difference'].sum()}")
print(f"Non-significant differences: {(~df_stats_results['significant_difference']).sum()}")

# Show first few rows
print(f"\nFirst 5 results:")
print(df_stats_results[['SHIFT_DOY', 'mean_control', 'mean_radiation', 'mean_diff', 
                  't_p_value', 'significant_difference']].head())

# Create color mapping for plotting
def assign_stats(row):
    if not row['control_normal'] or not row['radiation_normal'] or not row['equal_variances']:
        return 'Assumptions Not Met'  # First priority
    elif row['significant_difference']:
        return 'Significant'   # Second priority
    else:
        return 'Non Significant'  # Third priority

df_stats_results['STATS'] = df_stats_results.apply(assign_stats, axis=1)


df_shift_doy = (
    df_apsim
        .groupby('SHIFT_DOY')
        .agg(
            # SHIFT_DEGREE_DAYS_FROM_ANTHESIS
            SHIFT_DEGREE_DAYS_FROM_ANTHESIS_MEAN=('SHIFT_DEGREE_DAYS_FROM_ANTHESIS', 'mean'),
            SHIFT_DEGREE_DAYS_FROM_ANTHESIS_STD=('SHIFT_DEGREE_DAYS_FROM_ANTHESIS', 'std'),
            SHIFT_DEGREE_DAYS_FROM_ANTHESIS_STD_ERROR=('SHIFT_DEGREE_DAYS_FROM_ANTHESIS', 'sem'),

            # GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL
            GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL_MEAN=('GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL', 'mean'),
            GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL_STD=('GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL', 'std'),
            GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL_STD_ERROR=('GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL', 'sem'),

            # GRAIN_NUMBER_MATURITY
            GRAIN_NUMBER_MATURITY_MEAN=('GRAIN_NUMBER_MATURITY', 'mean'),
            GRAIN_NUMBER_MATURITY_STD=('GRAIN_NUMBER_MATURITY', 'std'),
            GRAIN_NUMBER_MATURITY_STD_ERROR=('GRAIN_NUMBER_MATURITY', 'sem'),
        )
        .reset_index()
)

df_apsim_to_plot = df_shift_doy.merge(df_stats_results, on='SHIFT_DOY')

df_apsim_to_plot['SITE'] = "APSIMNG" 

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.lines import Line2D

# Clean, publication-style defaults
sns.set_theme(style="white", context="paper", font_scale=1.1)

plt.rcParams.update({
    "text.color": "black",
    "axes.labelcolor": "black",
    "xtick.color": "black",
    "ytick.color": "black",
    "axes.edgecolor": "black",
})

# Color-blind friendly, high-contrast palette
fischer_color = "#0072B2"   # blue
apsim_color   = "#D55E00"   # orange

# Sort line data so the trend line is drawn correctly
df_line = (
    df_fischer_trend_line
    .dropna(subset=["DEGREE_DAYS_FROM_ANTHESIS", "GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL"])
    .sort_values("DEGREE_DAYS_FROM_ANTHESIS")
)

df_apsim = df_apsim_to_plot.dropna(
    subset=["SHIFT_DEGREE_DAYS_FROM_ANTHESIS_MEAN", "GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL_MEAN"]
)

df_fischer_plot = df_fischer.dropna(
    subset=["DEGREE_DAYS_FROM_ANTHESIS", "GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL"]
)

fig, ax = plt.subplots(figsize=(3.2, 2.4), dpi=300)
fig.patch.set_alpha(0)
ax.set_facecolor("none")

# Trend line: same color as Fischer points
sns.lineplot(
    data=df_line,
    x="DEGREE_DAYS_FROM_ANTHESIS",
    y="GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL",
    ax=ax,
    color=fischer_color,
    linewidth=2,
    errorbar=None,
    legend=False,
    zorder=3,
)

# APSIM points: one contrasting colour
sns.scatterplot(
    data=df_apsim,
    x="SHIFT_DEGREE_DAYS_FROM_ANTHESIS_MEAN",
    y="GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL_MEAN",
    ax=ax,
    color=apsim_color,
    s=36,
    marker="o",
    edgecolor="none",
    linewidth=0,
    legend=False,
    zorder=2,
)

# Fischer points: slightly larger, black outline
sns.scatterplot(
    data=df_fischer_plot,
    x="DEGREE_DAYS_FROM_ANTHESIS",
    y="GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL",
    ax=ax,
    color=fischer_color,
    s=48,
    marker="o",
    edgecolor="black",
    linewidth=0.7,
    legend=False,
    zorder=4,
)

ax.set_xlim(left=-1250)
ax.set_xlim(right=750)

# Vertical reference line at x = 0
ax.axvline(0, color="black", linewidth=0.9, linestyle="--", zorder=1)
ax.axhline(100, color="black", linewidth=0.9, linestyle="--", zorder=1)

# Minimal styling for graphical abstract use
ax.set_xlabel("Degree days from anthesis (°C)")
ax.set_ylabel("Grain number\n(% of unshaded control)")
ax.tick_params(axis="both", which="both", length=2.5, width=0.8, labelsize=8)

# Remove unnecessary visual clutter
sns.despine(ax=ax, top=True, right=True)

# Optional: tighten limits a little for a cleaner composition
# ax.set_xlim(left=min(0, ax.get_xlim()[0]))

# Very simple legend
handles = [
    #Line2D([0], [0], color=fischer_color, lw=1.5, label="Fischer trend"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=apsim_color,
           markeredgecolor="none", markersize=6, label="APSIM NextGen"),
    Line2D([0], [0], marker="o", color="none", markerfacecolor=fischer_color,
           markeredgecolor="black", markeredgewidth=0.7, markersize=6, label="Expt 74A\n(Fischer 1985)"),
]
ax.legend(
    handles=handles,
    frameon=False,
    loc="lower left",
    fontsize=8,
    handlelength=0.3,
    borderaxespad=0.001,
)

plt.tight_layout()

# Transparent export
plt.savefig(
    f"graphical_abstract_plot_{SINGLE_CULTIVAR}_{SINGLE_SITE}.png",
    dpi=600,
    #transparent=True,
    bbox_inches="tight",
    pad_inches=0.04,
)

print('finished :)')