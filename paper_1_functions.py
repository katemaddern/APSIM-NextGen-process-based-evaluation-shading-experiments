"""
paper_1_functions.py
--------------------
Shared helper functions and plotting settings for the paper_1 workflow.

Figure settings follow the European Journal of Agronomy guide for authors and
Elsevier's artwork and media instructions:
  - Widths: minimal 30 mm, single column 90 mm, 1.5 column 140 mm,
    double column (full width) 190 mm.
  - Lettering: ~7 pt for normal text at final printed size, never below 6 pt
    (sub/superscripts). We use 8-10 pt to stay comfortably above this.
  - Fonts: Arial (or Helvetica), Courier, Symbol, Times. Embed fonts.
  - Resolution: 1000 dpi line art (graphs), 500 dpi combination art,
    300 dpi halftones (photographs).
  - Formats: EPS or PDF for vector graphics; TIFF for bitmaps.
  - Colour: use colour-blind-safe palettes; don't rely on colour alone.
  - Each figure must be a separate file (e.g. Figure_1, Figure_2 ...).

Usage in any script
-------------------
    from paper_1_functions import *          # rcParams are applied on import
    # or, more explicitly:
    import paper_1_functions as pf

    fig, ax = plt.subplots(figsize=pf.fig_size('double', aspect=8/12))
    ax.set_xticklabels(pf.format_site_names(pf.site_order))
    pf.save_figure(fig, 'Figure_3')          # -> Figure_3.pdf + Figure_3.tif

If another library (e.g. seaborn.set_theme) overwrites the rcParams, call
apply_journal_style() again afterwards.
"""

import os
import sys
import time
import datetime
import calendar
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.transforms as mtransforms
from matplotlib.ticker import MultipleLocator
from scipy import stats
from statsmodels.stats.multitest import multipletests

SCRIPTS_BASE = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_BASE not in sys.path:
    sys.path.insert(0, SCRIPTS_BASE)

from config_loader import cfg


########################################################################################
# JOURNAL SPEC CONSTANTS (European Journal of Agronomy / Elsevier)
########################################################################################
MM_TO_INCH = 1 / 25.4

# ── Figure widths (Elsevier artwork sizing) ─────────────────────────────────
FIG_WIDTH_MM = {
    'minimal': 30,
    'single':  90,
    '1.5':     140,
    'double':  190,   # full page width
}
FIG_WIDTH_SINGLE_IN = FIG_WIDTH_MM['single'] * MM_TO_INCH   # 3.54 in
FIG_WIDTH_ONEHALF_IN = FIG_WIDTH_MM['1.5'] * MM_TO_INCH     # 5.51 in
FIG_WIDTH_DOUBLE_IN = FIG_WIDTH_MM['double'] * MM_TO_INCH   # 7.48 in

# Defaults kept for backwards compatibility with existing scripts
FIG_WIDTH_IN = FIG_WIDTH_DOUBLE_IN
FIG_HEIGHT_IN = FIG_WIDTH_IN * (8 / 12)   # 12:8 (3:2) aspect ratio

MAX_FIG_HEIGHT_MM = 240

# ── Resolution ──────────────────────────────────────────────────────────────
DPI_LINE_ART = 1000   # graphs, charts, line drawings
DPI_COMBINATION = 500   # line art + photographs
DPI_HALFTONE = 300   # photographs only
DPI = DPI_LINE_ART   # default for saving
DPI_SCREEN = 150   # interactive display only (1000 dpi on screen is huge/slow)

# ── Font sizes (pt, at final printed size) ──────────────────────────────────
FONT_SIZE_MIN = 6     # absolute floor (sub/superscripts) — never go below
FONT_SIZE_SMALL = 8     # stage labels, legend, annotations
FONT_SIZE_NORMAL = 9
FONT_SIZE_TITLE = 10

FONT_FAMILY = 'sans-serif'
# Arial/Helvetica are Elsevier's recommended sans fonts. Liberation Sans is
# metrically identical to Arial and is the usual substitute on Linux/HPC.
FONT_SANS = ['Arial', 'Helvetica', 'Liberation Sans', 'DejaVu Sans']

# ── Line widths (pt) ────────────────────────────────────────────────────────
LW_THIN = 0.5    # spines, ticks, reference lines
LW_MED = 0.75   # error bars, annotation arrows, default lines
LW_THICK = 1.0    # main marker edges
LW_LEGEND = 1.25
LW_HORIZONTAL = 1.5

# ── Save defaults ───────────────────────────────────────────────────────────
SAVE_FORMATS = ('pdf', 'tif')   # vector + 1000 dpi bitmap


########################################################################################
# GLOBAL rcParams
########################################################################################
JOURNAL_RCPARAMS = {
    # Fonts
    'font.family':        FONT_FAMILY,
    'font.sans-serif':    FONT_SANS,
    'mathtext.default':   'regular',   # $t\ ha^{-1}$ renders in the body font

    'font.size':          FONT_SIZE_NORMAL,
    'axes.titlesize':     FONT_SIZE_TITLE,
    'axes.labelsize':     FONT_SIZE_NORMAL,
    'xtick.labelsize':    FONT_SIZE_NORMAL,
    'ytick.labelsize':    FONT_SIZE_NORMAL,
    'legend.fontsize':    FONT_SIZE_SMALL,
    'legend.title_fontsize': FONT_SIZE_SMALL,
    'figure.titlesize':   FONT_SIZE_TITLE,

    # Lines and ticks
    'axes.linewidth':     LW_THIN,
    'xtick.major.width':  LW_THIN,
    'ytick.major.width':  LW_THIN,
    'xtick.minor.width':  0.3,
    'ytick.minor.width':  0.3,
    'xtick.major.size':   2.5,
    'ytick.major.size':   2.5,
    'xtick.minor.size':   1.5,
    'ytick.minor.size':   1.5,
    'lines.linewidth':    LW_MED,
    'patch.linewidth':    LW_THIN,
    'errorbar.capsize':   1.5,

    # Figure / saving
    'figure.figsize':     (FIG_WIDTH_IN, FIG_HEIGHT_IN),
    'figure.dpi':         DPI_SCREEN,
    'savefig.dpi':        DPI,
    'savefig.bbox':       'standard',   # keep exact journal width (no tight crop)
    'savefig.facecolor':  'white',

    # Embed TrueType fonts so text stays editable (Elsevier: embed fonts)
    'ps.fonttype':        42,
    'pdf.fonttype':       42,
    'svg.fonttype':       'none',
}


def apply_journal_style():
    """Apply the journal rcParams. Called automatically on import; call again
    if another library (e.g. seaborn.set_theme) overwrites them."""
    mpl.rcParams.update(JOURNAL_RCPARAMS)


apply_journal_style()


########################################################################################
# FUNCTIONS
########################################################################################
def fig_size(width='double', aspect=8 / 12, height_mm=None):
    """
    Return (width_in, height_in) for a journal-compliant figure.

    Parameters
    ----------
    width : {'minimal', 'single', '1.5', 'double'} or float
        Named Elsevier column width, or a custom width in mm.
    aspect : float
        height / width ratio (ignored if height_mm is given).
    height_mm : float, optional
        Explicit height in mm.
    """
    width_mm = FIG_WIDTH_MM[width] if isinstance(width, str) else float(width)
    width_in = width_mm * MM_TO_INCH
    height_in = height_mm * MM_TO_INCH if height_mm is not None else width_in * aspect
    return (width_in, height_in)


# Site names that need splitting into separate words before capitalising.
# Add any other run-together names here.
SITE_NAME_OVERRIDES = {
    'lakebolac': 'lake bolac',
}


def format_site_name(site):
    """
    Convert a raw site key into a display label.

    'lakebolac'   -> 'Lake Bolac'
    'longerenong' -> 'Longerenong'
    """
    name = SITE_NAME_OVERRIDES.get(site.strip().lower(), site.strip())
    return ' '.join(word.capitalize() for word in name.split())


def format_site_names(sites):
    """Vectorised format_site_name for a list, tuple, Index or Series."""
    if isinstance(sites, (pd.Series, pd.Index)):
        return sites.map(format_site_name)
    return [format_site_name(s) for s in sites]

# Rename Cultivar names for display in figures. Keys are the raw cultivar names, values are the display names.
CULTIVAR_NAME_OVERRIDES = {
    'SpringVQQ': 'Spring Very Quick-Quick',
    'SpringQ': 'Spring Quick',
    'SpringQM': 'Spring Quick-Mid',
    'SpringM': 'Spring Mid',
    'SpringMS': 'Spring Mid-Slow',
    'SpringS': 'Spring Slow',
    'SpringSVS': 'Spring Slow-Very Slow',
    'SpringVS': 'Spring Very Slow',
    'WinterVQ': 'Winter Very Quick',
    'WinterQ': 'Winter Quick',
    'WinterM': 'Winter Mid',
    'WinterVS': 'Winter Very Slow',
}

def format_cultivar_name(cultivar):
    """
    Convert a raw cultivar key into a display label.

    'SpringVQQ'   -> 'Spring Very Quick-Quick'
    'WinterVQ' -> 'Winter Very Quick'
    """
    return CULTIVAR_NAME_OVERRIDES.get(cultivar, cultivar)

def format_cultivar_names(cultivars):
    """Vectorised format_cultivar_name for a list, tuple, Index or Series."""
    if isinstance(cultivars, (pd.Series, pd.Index)):
        return cultivars.map(format_cultivar_name)
    return [format_cultivar_name(c) for c in cultivars]


VECTOR_FORMATS = ('pdf', 'eps', 'ps', 'svg')


def save_figure(fig, name, out_dir='.', formats=SAVE_FORMATS, dpi=DPI,
                vector_dpi=DPI_COMBINATION, close=True):
    """
    Save a figure in journal-ready formats.

    Default writes a vector PDF (fonts embedded) and a 1000 dpi LZW-compressed
    TIFF. Rasterized layers inside vector files (e.g. thousands of raw points)
    are written at vector_dpi (500 dpi, Elsevier 'combination art'), which keeps
    PDF/EPS files small. Returns the list of written paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for fmt in formats:
        fmt = fmt.lower().lstrip('.')
        path = os.path.join(out_dir, f'{name}.{fmt}')
        fmt_dpi = vector_dpi if fmt in VECTOR_FORMATS else dpi
        kwargs = {'dpi': fmt_dpi, 'format': 'tiff' if fmt in ('tif', 'tiff') else fmt}
        if fmt in ('tif', 'tiff'):
            kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}
        fig.savefig(path, **kwargs)
        paths.append(path)
    if close:
        plt.close(fig)
    return paths


########################################################################################
# CONSTANTS FOR PLOTTING
########################################################################################
# NOTE: SITE_ORDER is also defined in config.sh and available via cfg.SITE_ORDER.
# Prefer that as the single source of truth; this copy is kept for convenience.
site_order = [
    'waikerie', 'mildura', 'lameroo', 'birchip',
    'bordertown', 'longerenong', 'millicent', 'lakebolac'
]

# Display labels in the same order, e.g. ['Waikerie', ..., 'Lake Bolac']
site_labels = format_site_names(site_order)
site_label_dict = dict(zip(site_order, site_labels))

# One fixed colour per site, used in every figure.
# Colour-blind-safe qualitative palette (Paul Tol 'muted').
site_color_dict = {
    'waikerie':    '#332288',
    'mildura':     '#88CCEE',
    'lameroo':     '#44AA99',
    'birchip':     '#117733',
    'bordertown':  '#999933',
    'longerenong': '#CC6677',
    'millicent':   '#882255',
    'lakebolac':   '#AA4499',
}

cultivar_order = [
    'SpringVQQ', 'SpringQ', 'SpringQM', 'SpringM', 'SpringMS', 'SpringS', 'SpringSVS',
    'SpringVS', 'WinterVQ', 'WinterQ', 'WinterM', 'WinterVS',
]

panel_letters = 'abcdefghijklmnopqrstuvwxyz'

cultivar_color_dict = {
    'SpringQ':    '#F9C80E',
    'SpringQM':   '#F3941E',
    'SpringM':    '#E8541E',
    'SpringMS':   '#D62839',
    'SpringS':    '#B0228C',
    'SpringSVS':  '#7B2D8B',
    'SpringVS':   '#2E9E5B',
    'WinterVQ':   '#1C8C82',
    'WinterQ':    '#1E6FA8',
    'WinterM':    '#1B4B8C',
    'WinterVS':   '#0F2A52',
}

# Critical-period definitions: plotting order (top bar first), legend label and colour.
# Keys match the column names, e.g. CUM_DEGREE_DAY_START_<KEY>_CRIT_PERIOD
# and DRA_CONT_START_<KEY>_CRIT_PERIOD.
cp_definition_order = [
    'FISCHER_2024', 'ABBATE_1997', 'SLAFER_2021', 'PORKER_2025',
    'DRECCER_2000', 'FISCHER_1985', 'SADRAS_2022', 'SLAFER_2023',
]

cp_definition_label_dict = {
    'FISCHER_2024': 'Fischer et al. (2024)',
    'ABBATE_1997':  'Abbate et al. (1997)',
    'SLAFER_2021':  'Slafer et al. (2021)',
    'PORKER_2025':  'Porker et al. (2025)',
    'DRECCER_2000': 'Dreccer et al. (2000)',
    'FISCHER_1985': 'Fischer (1985)',
    'SADRAS_2022':  'Sadras et al. (2022)',
    'SLAFER_2023':  'Slafer et al. (2023)',
}

cp_definition_color_dict = {      # same colours as the current figures ('tab:' palette)
    'FISCHER_2024': '#d62728',    # tab:red
    'ABBATE_1997':  '#1f77b4',    # tab:blue
    'SLAFER_2021':  '#ff7f0e',    # tab:orange
    'PORKER_2025':  '#2ca02c',    # tab:green
    'DRECCER_2000': '#9467bd',    # tab:purple
    'FISCHER_1985': '#8c564b',    # tab:brown
    'SADRAS_2022':  '#e377c2',    # tab:pink
    'SLAFER_2023':  '#bcbd22',    # tab:olive
}

########################################################################################
########################################################################################
# SHARED SETTINGS FOR THE SHADING FIGURES
# Change a value here and re-run the figure scripts: every figure picks it up.
########################################################################################
########################################################################################

# ── Output ──────────────────────────────────────────────────────────────────
# All figure scripts save their figures and tables here.
OUTPUT_DIR = getattr(cfg, 'SECOND_DRAFT_DIR', '.')
# OUTPUT_DIR = getattr(cfg, 'DRYLAND_TEST_FIGS_DIR', '.')
# Formats written by the figure scripts. ('pdf', 'png') for drafts; use
# SAVE_FORMATS = ('pdf', 'tif') (or add 'eps') for the final submission.
FIGURE_FORMATS = ('pdf', 'png')


def output_dir():
    """Create (if needed) and return the output folder for figures and tables."""
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    return out


def save(fig, name, formats=None, close=True):
    """Save a figure to output_dir() in FIGURE_FORMATS and print the paths."""
    paths = save_figure(fig, name, out_dir=str(output_dir()),
                        formats=formats or FIGURE_FORMATS, close=close)
    for p in paths:
        print('Saved', p)
    return paths


def save_table(df, name, index=False):
    """Save a table as CSV to output_dir()."""
    path = output_dir() / (name if name.endswith('.csv') else f'{name}.csv')
    df.to_csv(path, index=index)
    print('Saved', path)
    return path


def start_script(script_file):
    """Print the script name and start time; returns the start time for finish_script()."""
    print(f'Script: {os.path.abspath(script_file)}')
    print(f'Started: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}')
    print(f'Outputs: {output_dir()}')
    return time.time()


def finish_script(start):
    print(f'Finished in {(time.time() - start) / 60:.1f} min')


# ── Simulation labels and columns ───────────────────────────────────────────
CONTROL_LABEL = 'control'      # VARIABLE value of the unshaded control runs
SHADED_LABEL = 'radiation'     # VARIABLE value of the shaded runs
YEAR_COL = 'YEAR'

# Shading timing on every x axis: thermal time (°Cd) from anthesis to this point
# of the shading window. 'MID' = middle of the window (= SHIFT_DOY).
SHADING_POINT = 'MID'          # 'START', 'MID' or 'END'
X_COL = 'DD_FROM_ANTHESIS'     # name of the computed x column
DD_ANTHESIS_COL = 'CUM_DEGREE_DAY_ANTHESIS_STAGE'


def dd_shading_col(point=None):
    return f'CUM_DEGREE_DAY_{point or SHADING_POINT}_SHADING'


def pct_col(var):
    """Column holding var as a percentage of the same-year unshaded control."""
    return f'{var}_PERCENTAGE_CONTROL'


def raw_var(col):
    """'GRAIN_NUMBER_MATURITY_PERCENTAGE_CONTROL' -> 'GRAIN_NUMBER_MATURITY'."""
    return col[:-len('_PERCENTAGE_CONTROL')] if col.endswith('_PERCENTAGE_CONTROL') else col


# ── Statistics ──────────────────────────────────────────────────────────────
ALPHA = 0.05            # significance level, applied to Holm-adjusted p values
CI_LEVEL = 0.95         # confidence intervals: t distribution with n - 1 df (n = years)
DD_BIN_WIDTH = 20.0     # °Cd. Shading windows are grouped into bins of this width
MIN_YEARS = 5           # bins with fewer paired years are not tested
MIN_WILCOXON_N = 6      # with < 6 non-zero pairs the two-sided Wilcoxon p can never be < 0.05
ZERO_TOL = 1e-10        # |% change| below this = no effect in that year

# Both tests are run for every figure; each script saves one figure per test.
TESTS = ('ttest', 'wilcoxon')
TEST_TITLES = {
    'ttest':    'Paired t-test (Wilcoxon signed-rank where differences are not normal), Holm-adjusted',
    'wilcoxon': 'Wilcoxon signed-rank test, Holm-adjusted',
}
TEST_SHORT = {'ttest': 'paired t-test', 'wilcoxon': 'Wilcoxon signed-rank'}

STATS_ORDER = ['Significant', 'Non Significant', 'Assumptions Not Met', 'Insufficient Data']
STATS_LEGEND_LABELS = {
    'Significant':         f'Significant (p < {ALPHA:g})',
    'Non Significant':     'Not significant',
    'Assumptions Not Met': f'Not normal, < {MIN_WILCOXON_N} pairs',
    'Insufficient Data':   f'Not tested (< {MIN_YEARS} years)',
}


# ── Yield determinants: one colour, label and marker each, used in every figure ──
# Okabe–Ito / Tol colour-blind-safe colours, all different from each other.
VARIABLE_STYLES = {
    'GRAIN_NUMBER_MATURITY':                 {'label': 'Grain number',                 'short': 'GN',    'color': '#009E73', 'marker': 'o',
                                              'units': 'Grain number (grains m$^{-2}$)'},
    'SPIKE_WEIGHT_ANTHESIS_STAGE':           {'label': 'Spike dry weight at anthesis', 'short': 'SDWa',  'color': '#0072B2', 'marker': 's',
                                              'units': 'Spike dry weight at anthesis (g m$^{-2}$)'},
    'CROP_GROWTH_RATE_CRITICAL_PERIOD':      {'label': 'Crop growth rate',             'short': 'CGR',   'color': '#D55E00', 'marker': '^',
                                              'units': 'Crop growth rate (g m$^{-2}$ d$^{-1}$)'},
    'DURATION_CRITICAL_PERIOD':              {'label': 'Duration',     'short': 'Dur',   'color': '#999933', 'marker': 'v',
                                              'units': 'Duration (days)'},
    'PARTITIONING_TO_SPIKE_CRITICAL_PERIOD': {'label': 'Partitioning to spike',        'short': 'Part',  'color': '#CC79A7', 'marker': 'D',
                                              'units': 'Partitioning to spike'},
    'FRUITING_EFFICIENCY_CRITICAL_PERIOD':   {'label': 'Fruiting efficiency',          'short': 'FE',    'color': '#882255', 'marker': 'P',
                                              'units': 'Fruiting efficiency (grains g$^{-1}$)'},
    'GRAIN_SIZE_MATURITY':                   {'label': 'Grain size',                   'short': 'GS',    'color': '#56B4E9', 'marker': 'X',
                                              'units': 'Grain size (g grain$^{-1}$)'},
    'YIELD_MATURITY':                        {'label': 'Yield',                        'short': 'Yield', 'color': '#E69F00', 'marker': 'h',
                                              'units': 'Yield (kg ha$^{-1}$)'},
}


def var_style(var):
    """Style dict for a raw variable or its _PERCENTAGE_CONTROL column."""
    return VARIABLE_STYLES[raw_var(var)]


def var_label(var):
    return var_style(var)['label']


def var_color(var):
    return var_style(var)['color']


# Water-supply scenarios (Figure 7)
DATASET_STYLES = {
    'dryland':   {'label': 'Standard growing conditions\n(Rainfed and local NBank Target)',                     'short': 'dryland',   'color': '#D55E00', 'marker': 'o', 'stage_linestyle': '--'},
    'irrigated': {'label': 'Expt74A conditions\n(Minimal water and N stress)', 'short': 'irrigated', 'color': '#0072B2', 'marker': 's', 'stage_linestyle': ':'},
}


# ── Growth stages ───────────────────────────────────────────────────────────
# Key = the part of the column name after CUM_DEGREE_DAY_ / DOY_CONT_.
# Value = (legend label, abbreviation drawn on the plots).
STAGES = {
    'GERMINATION':            ('Germination',                'G'),
    'EMERGENCE':              ('Emergence',                  'E'),
    'DOUBLE_RIDGE':           ('Double ridge',               'DR'),
    'MAX_SPIKELET_PRIMORDIA': ('Maximum spikelet primordia', 'MSP'),
    'FLAG_LEAF':              ('Flag leaf appearance',       'FLA'),
    'HEAD_EMERGENCE':         ('Head emergence',             'H'),
    'ANTHESIS_STAGE':         ('Anthesis',                   'A'),
    'MAX_GRAIN_LENGTH':       ('Maximum grain length',       'MGL'),
    'END_GRAIN_FILL':         ('End of grain filling',       'EGF'),
    'MATURITY':               ('Harvest ripe',               'HR'),
}
ANTHESIS = 'ANTHESIS_STAGE'

# Stages drawn on the shading-timing plots (those outside the x range are skipped)
STAGES_TO_SHOW = ['GERMINATION', 'EMERGENCE', 'DOUBLE_RIDGE', 'MAX_SPIKELET_PRIMORDIA', 'FLAG_LEAF', 'HEAD_EMERGENCE',
                  'ANTHESIS_STAGE', 'MAX_GRAIN_LENGTH', 'END_GRAIN_FILL', 'MATURITY']
# # Stages also drawn as a shaded min–max range across years
STAGE_RANGE_STAGES = ['FLAG_LEAF', 'MAX_GRAIN_LENGTH']
# Stages also drawn as a shaded min–max range across years: every shown stage except
# anthesis (anthesis is 0 °Cd by definition, so it has no range)
# STAGE_RANGE_STAGES = [s for s in STAGES_TO_SHOW if s != ANTHESIS]
# Stage timing comes from the control runs (one per year)
STAGE_RUNS = 'control'

STAGE_STYLE_DEFAULT = {'color': '#8C8C8C', 'linestyle': ':', 'linewidth': LW_THIN}
STAGE_STYLES = {                             # overrides of STAGE_STYLE_DEFAULT
    'ANTHESIS_STAGE':   {'color': '#000000', 'linestyle': '-',  'linewidth': LW_LEGEND},
    'FLAG_LEAF':        {'color': '#1B7837', 'linestyle': '--', 'linewidth': LW_MED},
    'MAX_GRAIN_LENGTH': {'color': '#B2182B', 'linestyle': '--', 'linewidth': LW_MED},
}
STAGE_RANGE_COLORS = {'FLAG_LEAF': '#E3F1E3', 'MAX_GRAIN_LENGTH': '#FBE3E3'}   # solid (no transparency)
STAGE_RANGE_COLOR_MULTI = '#EDEDED'   # faint grey span (single-site panels: stages without their own range colour)
STAGE_LABEL_FONTSIZE = 7
STAGE_LABEL_BOLD = ['ANTHESIS_STAGE']
STAGE_LABEL_Y = 0.985          # axes fraction (top of the label)
STAGE_TICK_LEN = 0.07          # axes fraction: tick length when several sites share a panel
STAGE_LABEL_EDGE = 0.03        # labels this close (axes fraction) to the left/right edge are aligned inwards
STAGE_LABEL_MIN_SEP = 0.07     # labels closer than this (axes fraction) are stacked on a lower row
STAGE_LABEL_ROW_STEP = 1.25    # vertical step between stacked label rows (multiples of the font size)
STAGE_LABEL_PRIORITY = ['ANTHESIS_STAGE', 'FLAG_LEAF', 'MAX_GRAIN_LENGTH']   # get the top row when labels collide


def stage_style(stage):
    return {**STAGE_STYLE_DEFAULT, **STAGE_STYLES.get(stage, {})}


def stage_label(stage):
    return STAGES[stage][0]


def stage_abbrev(stage):
    return STAGES[stage][1]


def stage_caption(stages=None):
    """'DR, double ridge; MSP, maximum spikelet primordia; ...' for figure captions."""
    stages = stages or STAGES_TO_SHOW
    return '; '.join(f'{STAGES[s][1]}, {STAGES[s][0].lower()}' for s in stages)


# ── Reference lines and data layers ─────────────────────────────────────────
CONTROL_LINE_STYLE = {'color': '#4D4D4D', 'linestyle': '--', 'linewidth': LW_MED, 'zorder': 2.5}   # above raw points
CONTROL_LINE_LABEL = 'Unshaded control'

RAW_SIZE = 1.0            # marker area (pt²) of individual simulations in the background
RAW_LIGHTEN = 0.75        # 0 = series colour, 1 = white (solid colour: no transparency needed)
CI_LINEWIDTH = LW_THIN    # 95% CI bars
STAT_SIZE = (9.0 * 0.35)         # marker area (pt²) of bin means
STAT_EDGE_WIDTH = LW_THIN
INSUFFICIENT_EDGE = '#8C8C8C'

Z_SPAN, Z_STAGE, Z_RAW, Z_CI, Z_STAT = 0, 1, 2, 3, 4

XLABEL_DD = 'Thermal time from anthesis to middle of shading period (°Cd)'
XLABEL_DD_START = 'Thermal time from anthesis to start of shading period (°Cd)'
XLABEL_DD_END = 'Thermal time from anthesis to end of shading period (°Cd)'
YLABEL_PCT = 'Percentage of unshaded control (%)'
DD_MAJOR, DD_MINOR = 500, 100      # x tick spacing (°Cd): labelled, unlabelled
DD_CMAP = 'viridis'                # colour scale for shading timing in °Cd (Figure 3)
Y_HEADROOM = 0.10                  # extra space above the data for stage labels (fraction of y range)


########################################################################################
# DATA PREPARATION
########################################################################################
def load_parquet(path, columns, filters=None, optional=()):
    """
    Read only the needed columns (and rows) of a parquet file with polars.
    filters: dict {column: value or list of values}. Columns in `optional` are read if present.
    """
    import polars as pl
    lazy = pl.scan_parquet(str(path))
    schema = lazy.collect_schema()
    missing = [c for c in columns if c not in schema]
    if missing:
        raise KeyError(f'Columns not in {path}: {missing}')
    cols = list(dict.fromkeys(list(columns) + [c for c in optional if c in schema]))
    lazy = lazy.select(cols)
    for col, val in (filters or {}).items():
        lazy = lazy.filter(pl.col(col).is_in(val) if isinstance(val, (list, tuple, set)) else pl.col(col) == val)
    df = lazy.collect().to_pandas()
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()
    return df


def stage_columns(prefix='CUM_DEGREE_DAY_'):
    return [f'{prefix}{s}' for s in STAGES]


CP_POINTS = ('START', 'END')


def _doy_dd_pairs():
    """(day column, °Cd column) pairs present in every run: shading window points and stages.
    Used to convert critical-period days to °Cd (add_cp_degree_days)."""
    pairs = [(f'DOY_CONT_{p}_SHADING', f'CUM_DEGREE_DAY_{p}_SHADING') for p in ('START', 'MID', 'END')]
    pairs += [(f'DOY_CONT_{s}', f'CUM_DEGREE_DAY_{s}') for s in STAGES]
    return pairs


def crit_period_columns(prefix=None):
    """Columns to read (as optional) for the critical-period bars: the °Cd columns if a file has
    them, otherwise the DOY_CONT_ columns plus the day/°Cd pairs used to convert them."""
    cols = [f'{p}{e}_{k}_CRIT_PERIOD' for p in ('CUM_DEGREE_DAY_', 'DOY_CONT_')
            for k in cp_definition_order for e in CP_POINTS]
    return cols + [c for pair in _doy_dd_pairs() for c in pair]


def add_cp_degree_days(df, keys=('DATASET', 'SITE', 'CULTIVAR', 'YEAR')):
    """
    Add CUM_DEGREE_DAY_START/END_<KEY>_CRIT_PERIOD from DOY_CONT_START/END_<KEY>_CRIT_PERIOD
    when the file only has the days. For each site x cultivar x year, every run's (day, °Cd)
    pairs (shading window start/mid/end and growth stages) form a day -> °Cd lookup for that
    season (thermal time depends only on the weather, not on shading); the critical-period days
    are interpolated in it. Days outside the lookup's range become NaN (no extrapolation).
    """
    todo = [(f'DOY_CONT_{e}_{k}_CRIT_PERIOD', f'CUM_DEGREE_DAY_{e}_{k}_CRIT_PERIOD')
            for k in cp_definition_order for e in CP_POINTS]
    todo = [(d, c) for d, c in todo if d in df.columns and c not in df.columns]
    if not todo:
        return df
    pairs = [(d, c) for d, c in _doy_dd_pairs() if d in df.columns and c in df.columns]
    if not pairs:
        print('WARNING: no day/°Cd column pairs to convert the critical periods to °Cd')
        return df
    keys = [k for k in keys if k in df.columns]
    lookup = pd.concat([df[keys + [d, c]].set_axis(keys + ['DOY', 'DD'], axis=1) for d, c in pairs]).dropna()
    lookup = lookup.groupby(keys + ['DOY'], as_index=False)['DD'].mean()
    tables = {k: (g['DOY'].to_numpy(), g['DD'].to_numpy())
              for k, g in lookup.sort_values(keys + ['DOY']).groupby(keys)}
    out = {c: np.full(len(df), np.nan) for _, c in todo}
    days = {d: df[d].to_numpy(dtype=float) for d, _ in todo}
    for k, idx in df.groupby(keys).indices.items():
        if k not in tables or len(tables[k][0]) < 2:
            continue
        x, y = tables[k]
        for d, c in todo:
            out[c][idx] = np.interp(days[d][idx], x, y, left=np.nan, right=np.nan)
    for c, v in out.items():
        df[c] = v
    n_missing = sum(int(np.isnan(v).sum() - df[d].isna().sum()) for (d, _), v in zip(todo, out.values()))
    print(f'Critical periods: converted {len(todo)} DOY_CONT_ columns to °Cd '
          f'({n_missing} values outside the day/°Cd lookup set to NaN)')
    return df


def drop_after_maturity(df, end_col='DOY_CONT_END_SHADING', maturity_col='DOY_CONT_MATURITY'):
    """Drop shaded windows that end after maturity. Control runs are always kept."""
    keep = (df['VARIABLE'] == CONTROL_LABEL) | (df[end_col] <= df[maturity_col])
    return df[keep].copy()


def load_shading_data(path, variables, filters=None, extra=(), points=None, optional=()):
    """
    Load a shading experiment for the shading-timing figures: id columns, the variables,
    thermal time at anthesis and at the shading window point(s), every CUM_DEGREE_DAY_<stage>
    column present, and drop shading windows that end after maturity.
    points: shading-window points needed ('START', 'MID', 'END'); default SHADING_POINT.
    """
    points = points or [SHADING_POINT]
    cols = (['SITE', 'CULTIVAR', YEAR_COL, 'VARIABLE', 'SHIFT_DOY', 'DOY_CONT_END_SHADING',
             'DOY_CONT_MATURITY', DD_ANTHESIS_COL] + [dd_shading_col(p) for p in points]
            + list(variables) + list(extra))
    df = load_parquet(path, list(dict.fromkeys(cols)), filters, optional=stage_columns() + list(optional))
    if df.empty:
        raise ValueError(f'No rows in {path} for {filters}')
    missing = [s for s in STAGES if f'CUM_DEGREE_DAY_{s}' not in df.columns]
    if missing:
        print(f'Stage columns not in the file (not drawn): {missing}')
    df = add_cp_degree_days(df)
    return drop_after_maturity(df)


def control_runs(df, keys):
    """The unshaded control runs, one per keys x YEAR (error if duplicated)."""
    ctrl = df[df['VARIABLE'] == CONTROL_LABEL]
    if 'SHIFT_DOY' in ctrl:
        ctrl = ctrl[ctrl['SHIFT_DOY'] == 0]
    dup = ctrl.duplicated(list(keys) + [YEAR_COL])
    if dup.any():
        raise ValueError(f'{dup.sum()} duplicate control runs for the same {list(keys) + [YEAR_COL]}')
    return ctrl


def percent_of_control(df, variables, keys=('SITE', 'CULTIVAR')):
    """
    Shaded runs with every variable as a percentage of the control run from the same
    keys x YEAR (same site, cultivar and weather). Adds CONTROL_<var> and <var>_PERCENTAGE_CONTROL.
    """
    keys = [k for k in keys if k in df.columns]
    ctrl = control_runs(df, keys)
    ctrl = ctrl[keys + [YEAR_COL] + list(variables)].rename(columns={v: f'CONTROL_{v}' for v in variables})
    shaded = df[df['VARIABLE'] == SHADED_LABEL].merge(ctrl, on=keys + [YEAR_COL], how='left',
                                                       validate='many_to_one')
    no_ctrl = shaded[[f'CONTROL_{v}' for v in variables]].isna().all(axis=1)
    if no_ctrl.any():
        print(f'WARNING: {no_ctrl.sum()} shaded runs have no same-year control and are dropped')
        shaded = shaded[~no_ctrl]
    for v in variables:
        shaded[pct_col(v)] = 100 * shaded[v] / shaded[f'CONTROL_{v}']
    return shaded


def add_dd_from_anthesis(df, point=None, out_col=X_COL):
    """x value: thermal time (°Cd) from anthesis to the start / middle / end of the shading window."""
    df[out_col] = df[dd_shading_col(point)] - df[DD_ANTHESIS_COL]
    return df


def present_in_order(values, order):
    """Items of `order` present in `values`, then any others (sorted)."""
    values = set(pd.unique(pd.Series(list(values))))
    return [v for v in order if v in values] + sorted(v for v in values if v not in order)


def dd_bin(x, width=None):
    """Centre of the thermal-time bin containing x (rounding stops float error splitting bin edges)."""
    width = width or DD_BIN_WIDTH
    return np.floor(np.round(np.asarray(x, dtype=float) / width, 9)) * width + width / 2


########################################################################################
# STATISTICS
########################################################################################
def t_ci(values, level=None):
    """
    Mean and confidence interval from the t distribution with n - 1 degrees of
    freedom (n = number of values, here years), NOT the normal 1.96.
    Returns (mean, low, high, n, sd). The CI has zero width if all values are equal
    and is NaN if n < 2.
    """
    level = level or CI_LEVEL
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return np.nan, np.nan, np.nan, 0, np.nan
    m = x.mean()
    if n < 2:
        return m, np.nan, np.nan, n, np.nan
    sd = x.std(ddof=1)
    half = stats.t.ppf(0.5 + level / 2, n - 1) * sd / np.sqrt(n)
    return m, m - half, m + half, n, sd


def _t_test_p(x):
    """Two-sided one-sample t-test of x against 0 (x = yearly % changes, i.e. a paired test).
    Defined when x does not vary: all 0 -> p = 1, all equal and non-zero -> p = 0."""
    if np.ptp(x) < 1e-9:
        return 1.0 if abs(x.mean()) < 1e-9 else 0.0
    return float(stats.ttest_1samp(x, 0.0).pvalue)


def paired_bin_tests(pct_values):
    """
    Tests for one bin. pct_values = one value per year: shaded as % of the same-year control.
    The pairs are (shaded, control) in the same year, tested on the % change, so the test and
    the plotted mean and CI use exactly the same numbers.
    """
    pct = np.asarray(pct_values, dtype=float)
    pct = pct[np.isfinite(pct)]
    x = pct - 100.0                                   # % change from control
    mean, lo, hi, n, sd = t_ci(pct)
    nz = x[np.abs(x) > ZERO_TOL]
    out = {'N_YEARS': n, 'MEAN': mean, 'SD': sd, 'CI_LOW': lo, 'CI_HIGH': hi,
           'N_NONZERO': len(nz), 'SHAPIRO_P': np.nan, 'DIFF_NORMAL': np.nan,
           'T_P': np.nan, 'WILCOXON_P': np.nan, 'NOTE': ''}
    if n < MIN_YEARS:
        out['NOTE'] = f'Not tested: {n} years (< {MIN_YEARS})'
        return out

    # Paired t-test + its normality check (Shapiro–Wilk on the differences)
    out['T_P'] = _t_test_p(x)
    if np.ptp(x) < 1e-9:
        out['DIFF_NORMAL'] = True                     # no variation: t-test result is exact
    else:
        out['SHAPIRO_P'] = float(stats.shapiro(x).pvalue)
        out['DIFF_NORMAL'] = out['SHAPIRO_P'] >= ALPHA

    # Wilcoxon signed-rank (zero differences dropped)
    if len(nz) == 0:
        out['WILCOXON_P'] = 1.0
        out['NOTE'] = 'All differences zero'
    else:
        try:
            out['WILCOXON_P'] = float(stats.wilcoxon(nz, alternative='two-sided').pvalue)
        except ValueError as e:
            out['NOTE'] = f'Wilcoxon failed: {e}'
    return out


def _holm(p):
    p = np.asarray(p, dtype=float)
    out = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    if ok.any():
        out[ok] = multipletests(p[ok], method='holm')[1]
    return out


def _label_wilcoxon(r):
    if r['N_YEARS'] < MIN_YEARS or not np.isfinite(r['WILCOXON_P_HOLM']):
        return 'Insufficient Data'
    if 0 < r['N_NONZERO'] < MIN_WILCOXON_N:
        return 'Insufficient Data'
    return 'Significant' if r['WILCOXON_P_HOLM'] < ALPHA else 'Non Significant'


def _label_ttest(r):
    """Paired t-test where the differences are normal; Wilcoxon where they are not."""
    if r['N_YEARS'] < MIN_YEARS or not np.isfinite(r['T_P_HOLM']):
        return 'Insufficient Data'
    if r['DIFF_NORMAL'] is True or r['DIFF_NORMAL'] == 1:
        return 'Significant' if r['T_P_HOLM'] < ALPHA else 'Non Significant'
    w = _label_wilcoxon(r)
    return 'Assumptions Not Met' if w == 'Insufficient Data' else w


def check_ci_consistency(summary, test, verbose=True):
    """
    A bin whose 95% CI includes 100% (no change from control) is not shown as significant.
    For the t-test on normal differences this can never happen (Holm p >= raw p, and raw
    p < 0.05 <=> the 95% t CI excludes 100%). It can happen for the Wilcoxon test, which tests
    the median rather than the mean; those bins are relabelled 'Non Significant'.
    """
    col = f'STATS_{test.upper()}'
    crosses = (summary['CI_LOW'] <= 100) & (summary['CI_HIGH'] >= 100)
    bad = (summary[col] == 'Significant') & crosses
    summary[f'CI_OVERRIDE_{test.upper()}'] = bad
    if bad.any():
        summary.loc[bad, col] = 'Non Significant'
    if verbose:
        print(f'  CI check ({TEST_SHORT[test]}): {int(bad.sum())} significant bins had a 95% CI '
              f'including 100% and were relabelled non-significant')
    return summary


def bin_per_year(shaded, value_cols, group_cols, x_col=X_COL, bin_width=None):
    """
    One row per group x VAR x DD_BIN x YEAR: the mean of that year's shaded windows in the bin.
    So every year counts once per bin, however many of its windows fall in the bin.
    """
    d = shaded.dropna(subset=[x_col]).copy()
    d['DD_BIN'] = dd_bin(d[x_col], bin_width)
    keys = list(group_cols) + ['DD_BIN', YEAR_COL]
    per_year = d.groupby(keys, as_index=False).agg(**{'X': (x_col, 'mean')},
                                                   **{c: (c, 'mean') for c in value_cols})
    long = per_year.melt(id_vars=keys + ['X'], value_vars=list(value_cols), var_name='VAR', value_name='PCT')
    long['VAR'] = long['VAR'].map(raw_var)
    return long.dropna(subset=['PCT'])


def bin_summary(per_year, group_cols, verbose=True):
    """
    Mean, t-based 95% CI and BOTH tests for every group x VAR x DD_BIN.
    Holm correction across the bins of each group x VAR, separately for each test.
    Columns: STATS_TTEST and STATS_WILCOXON hold the label used for the marker fill.
    """
    keys = list(group_cols) + ['VAR', 'DD_BIN']
    rows = []
    for k, g in per_year.groupby(keys, sort=True):
        rows.append({**dict(zip(keys, k)), 'X_MEAN': g['X'].mean(), **paired_bin_tests(g['PCT'])})
    s = pd.DataFrame(rows)
    fam = list(group_cols) + ['VAR']
    s['T_P_HOLM'] = s.groupby(fam)['T_P'].transform(_holm)
    s['WILCOXON_P_HOLM'] = s.groupby(fam)['WILCOXON_P'].transform(_holm)
    s['DIFF_NORMAL'] = s['DIFF_NORMAL'].astype(object)
    s['STATS_TTEST'] = s.apply(_label_ttest, axis=1)
    s['STATS_WILCOXON'] = s.apply(_label_wilcoxon, axis=1)
    s['TEST_USED_TTEST'] = np.where(s['STATS_TTEST'] == 'Insufficient Data', '',
                                    np.where(s['DIFF_NORMAL'] == True, 't-test', 'Wilcoxon'))
    for t in TESTS:
        s = check_ci_consistency(s, t, verbose=verbose)
    return s


def summarise_shading(shaded, variables, group_cols, x_col=X_COL, bin_width=None, verbose=True):
    """percent_of_control output -> (per-year table, bin summary with both tests)."""
    per_year = bin_per_year(shaded, [pct_col(v) for v in variables], group_cols, x_col, bin_width)
    summary = bin_summary(per_year, group_cols, verbose=verbose)
    if verbose:
        for t in TESTS:
            counts = summary.groupby('VAR')[f'STATS_{t.upper()}'].value_counts().unstack(fill_value=0)
            print(f'\n  {TEST_SHORT[t]} labels per variable:\n{counts.to_string()}')
    return per_year, summary


def stage_summary(df, group_cols, prefix='CUM_DEGREE_DAY_', anthesis_col=None, runs=None):
    """
    Mean, min and max of every growth stage relative to anthesis (°Cd for CUM_DEGREE_DAY_,
    days for DOY_CONT_), across years, for every group (e.g. SITE x CULTIVAR).
    Uses the control runs (one per year) unless runs='shaded'.
    Returns a long table: group_cols + STAGE, MEAN, MIN, MAX, N.
    """
    runs = runs or STAGE_RUNS
    anthesis_col = anthesis_col or f'{prefix}{ANTHESIS}'
    group_cols = [c for c in group_cols if c in df.columns]
    src = df[df['VARIABLE'] == (CONTROL_LABEL if runs == 'control' else SHADED_LABEL)]
    if runs == 'control' and 'SHIFT_DOY' in src:
        src = src[src['SHIFT_DOY'] == 0]
    frames = []
    for st in STAGES:
        col = f'{prefix}{st}'
        if col not in src.columns:
            continue
        rel = src[group_cols].copy()
        rel['VALUE'] = src[col] - src[anthesis_col]
        g = rel.dropna().groupby(group_cols)['VALUE'].agg(MEAN='mean', MIN='min', MAX='max', N='count').reset_index()
        g['STAGE'] = st
        frames.append(g)
    if not frames:
        return pd.DataFrame(columns=group_cols + ['STAGE', 'MEAN', 'MIN', 'MAX', 'N'])
    return pd.concat(frames, ignore_index=True)


def stages_for(stage_table, **selection):
    """Rows of a stage_summary table for one group, indexed by STAGE."""
    t = stage_table
    for col, val in selection.items():
        t = t[t[col] == val]
    return t.set_index('STAGE')


def significant_windows(summary, test, group_cols):
    """First / last bin (mean x) labelled Significant, per group x VAR."""
    col = f'STATS_{test.upper()}'
    sig = summary[summary[col] == 'Significant']
    return (sig.groupby(list(group_cols) + ['VAR'])['X_MEAN']
               .agg(first_significant='min', last_significant='max', n_significant_bins='count')
               .reset_index())


########################################################################################
# DRAWING
########################################################################################
def lighten(color, amount=RAW_LIGHTEN):
    """Mix a colour with white (amount 0 = unchanged, 1 = white). Solid, so it survives EPS."""
    r, g, b = mcolors.to_rgb(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount)


def stats_marker_style(label, color):
    """Marker face/edge colour for a stats label. The same encoding is used in every figure:
       filled = significant, open = not significant, light fill = not normal and too few
       pairs for Wilcoxon, open with a pale edge = not tested."""
    if label == 'Significant':
        return {'facecolor': color, 'edgecolor': color}
    if label == 'Non Significant':
        return {'facecolor': 'white', 'edgecolor': color}
    if label == 'Assumptions Not Met':
        # return {'facecolor': lighten(color, 0.6), 'edgecolor': color}
        return {'facecolor': 'grey', 'edgecolor': color}
    return {'facecolor': 'white', 'edgecolor': INSUFFICIENT_EDGE}


def draw_control_line(ax):
    ax.axhline(100, **CONTROL_LINE_STYLE)


def draw_raw(ax, x, y, color, size=None):
    """Individual simulations in the background (light, solid colour, rasterized)."""
    ax.scatter(x, y, s=size or RAW_SIZE, color=lighten(color), linewidths=0,
               zorder=Z_RAW, rasterized=True)


def draw_ci(ax, x, low, high, color):
    """Vertical 95% CI bars."""
    ok = np.isfinite(np.asarray(low, float)) & np.isfinite(np.asarray(high, float))
    ax.vlines(np.asarray(x)[ok], np.asarray(low)[ok], np.asarray(high)[ok], color=color,
              linewidth=CI_LINEWIDTH, zorder=Z_CI)


def draw_stat_points(ax, x, y, labels, color, marker='o', size=None):
    """Bin means, with the marker fill showing the test result (stats_marker_style)."""
    x, y, labels = np.asarray(x), np.asarray(y), np.asarray(labels)
    for lab in STATS_ORDER:
        m = labels == lab
        if m.any():
            ax.scatter(x[m], y[m], s=size or STAT_SIZE, marker=marker,
                       linewidths=STAT_EDGE_WIDTH, zorder=Z_STAT, **stats_marker_style(lab, color))


def draw_series(ax, summary, test, color, marker='o', raw=None, raw_x=X_COL, raw_y=None,
                show_raw=True, show_ci=True):
    """
    One series on a shading-timing plot: raw simulations (background), 95% CI bars and the
    bin means with the test result. summary = rows of bin_summary for this series.
    raw = shaded runs for this series with columns raw_x and raw_y.
    """
    if show_raw and raw is not None and len(raw):
        draw_raw(ax, raw[raw_x], raw[raw_y], color)
    s = summary.sort_values('X_MEAN')
    if show_ci:                       # no CI bar for untested bins (< MIN_YEARS years)
        c = s[s['N_YEARS'] >= MIN_YEARS]
        draw_ci(ax, c['X_MEAN'], c['CI_LOW'], c['CI_HIGH'], color)
    draw_stat_points(ax, s['X_MEAN'], s['MEAN'], s[f'STATS_{test.upper()}'], color, marker)
    return set(s[f'STATS_{test.upper()}'])


def _place_stage_labels(ax, items, y=None):
    """items: list of (x, stage). Every stage line inside the x range is labelled. A label
    closer than STAGE_LABEL_MIN_SEP to one already placed on a row moves down to the next
    free row, so overlapping labels are stacked instead of dropped. Higher-priority stages
    (STAGE_LABEL_PRIORITY) are placed first and so get the top row."""
    lo, hi = ax.get_xlim()
    span = hi - lo
    rank = {s: i for i, s in enumerate(STAGE_LABEL_PRIORITY)}
    items = sorted([(x, s) for x, s in items if np.isfinite(x) and lo <= x <= hi],
                   key=lambda t: (rank.get(t[1], len(rank)), t[0]))
    rows = []                                     # x positions already placed on each row
    for x, s in items:
        row = next((i for i, r in enumerate(rows)
                    if all(abs(x - p) / span >= STAGE_LABEL_MIN_SEP for p in r)), len(rows))
        if row == len(rows):
            rows.append([])
        rows[row].append(x)
        _stage_text(ax, x, s, y, row=row)


def _stage_text(ax, x, stage, y=None, row=0):
    lo, hi = ax.get_xlim()
    frac = (x - lo) / (hi - lo)
    ha = 'left' if frac < STAGE_LABEL_EDGE else 'right' if frac > 1 - STAGE_LABEL_EDGE else 'center'
    trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)
    if row:                                       # stacked label: shift down by whole rows
        dy = -row * STAGE_LABEL_ROW_STEP * STAGE_LABEL_FONTSIZE / 72
        trans = trans + mtransforms.ScaledTranslation(0, dy, ax.figure.dpi_scale_trans)
    ax.text(x, STAGE_LABEL_Y if y is None else y, stage_abbrev(stage), transform=trans,
            ha=ha, va='top', fontsize=STAGE_LABEL_FONTSIZE,
            fontweight='bold' if stage in STAGE_LABEL_BOLD else 'normal',
            color=stage_style(stage)['color'] if stage in STAGE_STYLES else '#4D4D4D',
            bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 0.4}, zorder=Z_STAT + 1, clip_on=True)


def draw_stages(ax, stages, stages_to_show=None, labels=True, linestyle=None, ranges=True):
    """
    Mean growth stages of ONE cultivar x site as full-height vertical lines, labelled with
    their abbreviation at the top. stages: stages_for(...) output (index STAGE, columns MEAN/MIN/MAX).
    Call AFTER setting the x limits (labels near the panel edge are skipped).
    linestyle overrides every stage's linestyle (e.g. one style per dataset).
    """
    stages_to_show = stages_to_show or STAGES_TO_SHOW
    lo, hi = ax.get_xlim()
    label_items = []
    for st in stages_to_show:
        if st not in stages.index:
            continue
        r = stages.loc[st]
        if ranges and st in STAGE_RANGE_STAGES and np.isfinite(r['MIN']):
            ax.axvspan(r['MIN'], r['MAX'], color=STAGE_RANGE_COLORS.get(st, '#EEEEEE'), linewidth=0, zorder=Z_SPAN)
            # ax.axvspan(r['MIN'], r['MAX'], color=STAGE_RANGE_COLORS.get(st, STAGE_RANGE_COLOR_MULTI), linewidth=0, zorder=Z_SPAN)
        if not lo <= r['MEAN'] <= hi:
            continue
        style = stage_style(st)
        if linestyle is not None and st != ANTHESIS:
            style = {**style, 'linestyle': linestyle}
        ax.axvline(r['MEAN'], zorder=Z_RAW + 0.5 if st == ANTHESIS else Z_STAGE, **style)
        label_items.append((r['MEAN'], st))
    if labels:
        _place_stage_labels(ax, label_items)
    ax.set_xlim(lo, hi)


def draw_stage_ticks(ax, stage_table, group_col, colors, stages_to_show=None, labels=True, ticks=True,
                     ranges=True):
    """
    Several cultivar x site groups in ONE panel (e.g. one marker colour per site).
    For every stage:
      - (ranges=True, stages in STAGE_RANGE_STAGES, e.g. FLA and MGL) a shaded span from the
        earliest to the latest value across all groups and years, in STAGE_RANGE_COLORS
      - one full-height line at the mean across groups, in the stage's own style
      - (ticks=True) a short tick at the top for each group's mean, in that group's colour
      - the abbreviation, written once
    Anthesis is 0 for every group, so it is a single line.
    Call AFTER setting the x limits.
    """
    stages_to_show = stages_to_show or STAGES_TO_SHOW
    lo, hi = ax.get_xlim()
    trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)
    label_items = []
    for st in stages_to_show:
        t = stage_table[stage_table['STAGE'] == st]
        if st == ANTHESIS:
            ax.axvline(0, zorder=Z_RAW + 0.5, **stage_style(ANTHESIS))
            label_items.append((0.0, ANTHESIS))
            continue
        if t.empty:
            continue
        # shaded range across all groups and years (e.g. green = FLA, red = MGL)
        if ranges and st in STAGE_RANGE_STAGES:
            s_lo, s_hi = t['MIN'].min(), t['MAX'].max()
            if np.isfinite(s_lo) and np.isfinite(s_hi):
                ax.axvspan(s_lo, s_hi, color=STAGE_RANGE_COLORS.get(st, STAGE_RANGE_COLOR_MULTI),
                           linewidth=0, zorder=Z_SPAN)
        # one full-height line at the mean across groups
        x = t['MEAN'].mean()
        if lo <= x <= hi:
            ax.axvline(x, zorder=Z_STAGE, **stage_style(st))
            label_items.append((x, st))
        # each group's mean as a coloured tick at the top
        if ticks:
            for _, r in t.iterrows():
                if lo <= r['MEAN'] <= hi:
                    ax.plot([r['MEAN'], r['MEAN']], [1 - STAGE_TICK_LEN, 1], transform=trans,
                            color=colors.get(r[group_col], 'black'), linewidth=LW_THICK,
                            solid_capstyle='butt', zorder=Z_STAGE, clip_on=False)
    if labels:
        _place_stage_labels(ax, label_items, y=(1 - STAGE_TICK_LEN - 0.01) if ticks else None)
    ax.set_xlim(lo, hi)


def panel_grid(n_panels, n_cols, height_mm, width='double', sharey=True, sharex=False):
    """Grid of panels (constrained layout), filled row by row; unused positions are hidden.
    Returns (fig, list of the n_panels axes)."""
    n_rows = int(np.ceil(n_panels / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=fig_size(width, height_mm=height_mm),
                             sharey=sharey, sharex=sharex, layout='constrained', squeeze=False)
    axes = axes.ravel()
    for ax in axes[n_panels:]:
        ax.set_visible(False)
    return fig, list(axes[:n_panels])


def shared_ylim(axes, summary=None, y_lim=None, include_ci=True, headroom=None):
    """Same y limits on every panel: y_lim if given, else the data range (incl. CI) + headroom."""
    if y_lim is None:
        lo = min(ax.get_ylim()[0] for ax in axes)
        hi = max(ax.get_ylim()[1] for ax in axes)
        if summary is not None and len(summary):
            summary = summary[summary['N_YEARS'] >= MIN_YEARS]
            cols = ['CI_LOW', 'CI_HIGH', 'MEAN'] if include_ci else ['MEAN']
            v = summary[cols].to_numpy(dtype=float)
            v = v[np.isfinite(v)]
            lo, hi = min(v.min(), 100), max(v.max(), 100)
            pad = (hi - lo) * 0.05
            lo, hi = lo - pad, hi + pad
        hi = hi + (hi - lo) * (Y_HEADROOM if headroom is None else headroom)
        y_lim = (lo, hi)
    for ax in axes:
        ax.set_ylim(*y_lim)
    return y_lim


# ── Critical-period definition bars ──────────────────────────────────────────
CP_LINEWIDTH = LW_LEGEND


def cp_summary(shaded, group_cols):
    """Mean start and end (°Cd from anthesis) of every critical-period definition per group,
    over the shaded runs. Columns: group_cols + DEFINITION, START, END, DURATION."""
    rows = []
    for key in cp_definition_order:
        s, e = f'CUM_DEGREE_DAY_START_{key}_CRIT_PERIOD', f'CUM_DEGREE_DAY_END_{key}_CRIT_PERIOD'
        if s not in shaded.columns or e not in shaded.columns:
            continue
        d = shaded[list(group_cols)].copy()
        d['DEFINITION'] = key
        d['START'] = shaded[s] - shaded[DD_ANTHESIS_COL]
        d['END'] = shaded[e] - shaded[DD_ANTHESIS_COL]
        rows.append(d)
    if not rows:
        print('WARNING: no critical-period columns (CUM_DEGREE_DAY_START/END_<KEY>_CRIT_PERIOD) '
              'in the data: CP bars are not drawn')
        return pd.DataFrame(columns=list(group_cols) + ['DEFINITION', 'START', 'END', 'DURATION'])
    out = pd.concat(rows).groupby(list(group_cols) + ['DEFINITION'], as_index=False)[['START', 'END']].mean()
    out['DURATION'] = out['END'] - out['START']
    return out


def cp_bar_positions(y_bottom, step):
    """y of each definition's bar (first definition on top, last at y_bottom)."""
    n = len(cp_definition_order)
    return {k: y_bottom + (n - 1 - i) * step for i, k in enumerate(cp_definition_order)}


def draw_cp_bars(ax, cp_rows, y_pos):
    """Horizontal bar from mean start to mean end for each definition in cp_rows."""
    for _, r in cp_rows.iterrows():
        if r['DEFINITION'] in y_pos:
            ax.hlines(y_pos[r['DEFINITION']], r['START'], r['END'], color=cp_definition_color_dict[r['DEFINITION']],
                      linewidth=CP_LINEWIDTH, zorder=Z_STAT)


def handles_cp(keys=None):
    keys = [k for k in cp_definition_order if keys is None or k in set(keys)]
    return [mlines.Line2D([], [], color=cp_definition_color_dict[k], linewidth=CP_LINEWIDTH,
                          label=cp_definition_label_dict[k]) for k in keys]


def handles_sites(sites, marker='o'):
    return handles_series([(format_site_name(s), site_color_dict[s], marker) for s in sites])


def format_dd_axis(ax, major=None, minor=None):
    ax.xaxis.set_major_locator(MultipleLocator(major or DD_MAJOR))
    ax.xaxis.set_minor_locator(MultipleLocator(minor or DD_MINOR))


def add_headroom(ax, frac=None):
    """Extra space above the data so the stage labels do not sit on the points."""
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + (hi - lo) * (Y_HEADROOM if frac is None else frac))


def x_limits(values, pad_frac=0.01):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    lo, hi = v.min(), v.max()
    pad = (hi - lo) * pad_frac
    return lo - pad, hi + pad


def panel_title(ax, k, text, **kw):
    ax.set_title(f'({panel_letters[k]}) {text}', loc='left', **kw)


# ── Legend handles (the same everywhere) ────────────────────────────────────
def handle_marker(label, color='black', marker='o', face=None, edge=None, size=4):
    return mlines.Line2D([], [], linestyle='None', marker=marker, markersize=size,
                         markerfacecolor=face or color, markeredgecolor=edge or color,
                         markeredgewidth=STAT_EDGE_WIDTH, label=label)


def handles_series(items):
    """items: list of (label, colour, marker) -> filled marker handles."""
    return [handle_marker(lab, c, m) for lab, c, m in items]


def handles_variables(variables):
    return handles_series([(var_label(v), var_color(v), 'o') for v in variables])


def handles_stats(test, used=None, color='black', marker='o'):
    """Marker-fill legend for the test result, titled by the test."""
    used = STATS_ORDER if used is None else [s for s in STATS_ORDER if s in used]
    out = []
    for s in used:
        st = stats_marker_style(s, color)
        out.append(handle_marker(STATS_LEGEND_LABELS[s], marker=marker, face=st['facecolor'], edge=st['edgecolor']))
    return out


def handles_data(raw_color='#808080'):
    return [handle_marker('Individual simulations', face=lighten(raw_color), edge=lighten(raw_color), size=2.5),
            mlines.Line2D([], [], color='black', linewidth=CI_LINEWIDTH, marker='|', markersize=6,
                          label=f'Bin mean ± {CI_LEVEL:.0%} CI'),
            mlines.Line2D([], [], label=CONTROL_LINE_LABEL,
                          **{k: v for k, v in CONTROL_LINE_STYLE.items() if k != 'zorder'})]


def handles_stages(stages_to_show=None, ticks=False, site_ticks_label='Mean stage per site (tick colour)',
                   ranges=True):
    """Legend for the stage lines. ticks=True: the multi-site version (draw_stage_ticks)."""
    stages_to_show = stages_to_show or STAGES_TO_SHOW
    out = []
    if ANTHESIS in stages_to_show:
        out.append(mlines.Line2D([], [], label=f'{stage_label(ANTHESIS)} (A)',
                                 **{**stage_style(ANTHESIS), 'linewidth': LW_LEGEND}))
    for st in stages_to_show:
        if st == ANTHESIS or st not in STAGE_STYLES:
            continue
        out.append(mlines.Line2D([], [], label=f'{stage_label(st)} ({stage_abbrev(st)})',
                                 **{**stage_style(st), 'linewidth': LW_LEGEND}))
        if ranges and st in STAGE_RANGE_STAGES:
            where = 'sites and years' if ticks else 'years'     # multi-site panels pool the sites
            out.append(mpatches.Patch(facecolor=STAGE_RANGE_COLORS[st], edgecolor='none',
                                      label=f'{stage_abbrev(st)} range across {where}'))
    if any(s not in STAGE_STYLES for s in stages_to_show):
        out.append(mlines.Line2D([], [], label='Other stages (labelled)',
                                 **{**STAGE_STYLE_DEFAULT, 'linewidth': LW_LEGEND}))
        if not ticks and any(s in STAGE_RANGE_STAGES and s not in STAGE_RANGE_COLORS for s in stages_to_show):
            out.append(mpatches.Patch(facecolor=STAGE_RANGE_COLOR_MULTI, edgecolor='none',
                                      label='Other stages: range across years'))
    if ticks:
        out.append(mlines.Line2D([], [], color='#4D4D4D', linewidth=LW_THICK, marker='|', linestyle='None',
                                 markersize=6, label=site_ticks_label))
    return out


def figure_legend(fig, groups, xlabel=None, **kw):
    """
    One legend below the panels (constrained layout keeps it outside the axes), with each
    group in its own column under a bold title. groups: list of (title, handles).
    xlabel: shared x-axis label, written centred above the legend (fig.supxlabel would be
    drawn on top of an 'outside' legend by constrained layout).
    """
    leg_kw = dict(frameon=False, fontsize=FONT_SIZE_SMALL, handlelength=1.8, handletextpad=0.5,
                  labelspacing=0.3, columnspacing=1.2)
    leg_kw.update(kw)
    groups = [(t, hs) for t, hs in groups if hs]
    n_rows = max(len(hs) + (1 if t else 0) for t, hs in groups)
    handles, labels = [], []
    for title, hs in groups:                      # legend fills column by column
        col_h, col_l = [], []
        if title:
            col_h.append(mpatches.Patch(visible=False))
            col_l.append(title)
        col_h += list(hs)
        col_l += [h.get_label() for h in hs]
        col_h += [mpatches.Patch(visible=False)] * (n_rows - len(col_h))
        col_l += [''] * (n_rows - len(col_l))
        handles += col_h
        labels += col_l
    leg = fig.legend(handles, labels, loc='outside lower center', ncols=len(groups),
                     title=xlabel, title_fontproperties={'size': FONT_SIZE_NORMAL}, **leg_kw)
    titles = {t for t, _ in groups if t}
    for txt in leg.get_texts():
        if txt.get_text() in titles:
            txt.set_fontweight('bold')
    return leg


def print_stage_caption(stages_to_show=None):
    print('Stage abbreviations for the caption:', stage_caption(stages_to_show))