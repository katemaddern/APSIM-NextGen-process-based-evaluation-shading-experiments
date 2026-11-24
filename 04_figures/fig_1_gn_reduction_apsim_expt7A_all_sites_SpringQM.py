#!/usr/bin/env python3
"""
Figure 1 – Timing of shading sensitivity: APSIM (all sites) vs Fischer (1985) Expt 74A.

Sections
  1. Settings          every choice you might want to change
  2. Fischer data      digitised grain number, radiation and trend line; thermal time from anthesis
  3. APSIM data        load, filter cultivar, % of same-year control, thermal time from anthesis;
                       radiation for each shading window from the raw daily CONTROL run (RAD_SOURCE)
  4. Paired tests      both tests (pf.TESTS) per site x thermal-time bin, Holm-corrected (pf)
  5. Mixed model       spline of timing + random year effect, simultaneous band, year bootstrap
  6. Sensitive period  onset / end from both analyses, in °Cd and days from anthesis
  7. Fischer agreement bias, RMSE, regression, CIs, timing shift; across-year mean and single years
  8. Figures           paired-test version (one per test) and mixed-model version
  9. Tables            everything to CSV in pf.output_dir()

x axis: thermal time (°Cd) from anthesis to the MIDDLE of the shading window.
Bins: pf.DD_BIN_WIDTH °Cd; each year counts once per bin; mean and t-based 95% CI across years.

Run from the command line:
    python fig_1_shading_timing_by_site.py            # full analysis
    python fig_1_shading_timing_by_site.py --quick    # fewer simulations, for a quick check
Shared settings (colours, labels, stage lines, statistics) are in paper_1_functions.py.
"""
import argparse
import math
import re
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402
import matplotlib as mpl                  # noqa: E402
import matplotlib.pyplot as plt           # noqa: E402
import matplotlib.lines as mlines         # noqa: E402
import matplotlib.patches as mpatches     # noqa: E402
from scipy import stats                   # noqa: E402
import statsmodels.formula.api as smf     # noqa: E402
from patsy import dmatrix, build_design_matrices  # noqa: E402
import pyarrow.parquet as pq              # noqa: E402

SCRIPTS_BASE = Path(__file__).resolve().parents[1]
if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg             # noqa: E402
import paper_1_functions as pf            # noqa: E402

# ── Data locations ──────────────────────────────────────────────────────────
# Fischer (1985) digitised data and weather: stored with the scripts
FISCHER_DIR = Path(cfg.ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR)

# APSIM results: the full file if it exists, otherwise the limited file for upload
APSIM_FILE_FULL = Path(cfg.ALL_DATA_SHADED_DF)
APSIM_FILE_LIMITED = Path(cfg.LIMITED_SHADED_DF)
if APSIM_FILE_FULL.is_file():
    APSIM_FILE = APSIM_FILE_FULL
elif APSIM_FILE_LIMITED.is_file():
    APSIM_FILE = APSIM_FILE_LIMITED
else:
    raise FileNotFoundError(f'No APSIM data file found:\n  {APSIM_FILE_FULL}\n  {APSIM_FILE_LIMITED}')

CULTIVAR = cfg.EXAMPLE_CULTIVAR

FISCHER_WEATHER_FILE = 'fischer_1985_daily_temp_radiation.csv'   # daily weather, Table 1 Fischer 1975
FISCHER_GRAIN_FILE = 'fischer_grain_number_data.csv'             # digitised Fig. 1 points
FISCHER_RADIATION_FILE = 'fischer_radiation_data.csv'            # digitised Fig. 1 radiation
FISCHER_TREND_FILE = 'fischer_grain_number_data.csv'
# CHECK: the trend line is loaded from the SAME file as the grain-number points, so it just
# joins the points. Point this at the digitised trend line if you have one.
FISCHER_ANTHESIS_DAS = 86      # days after sowing to 50% anthesis (Fischer 1975, p. 610)
FISCHER_LABEL = 'Expt 74A (Fischer 1985)'

RESPONSE = 'GRAIN_NUMBER_MATURITY'

# Radiation in the top panels: mean daily incoming radiation over each shading window (14 days,
# SHIFT_DOY - 7 to SHIFT_DOY + 6 inclusive), taken from
#   'control': the unshaded control run of the same site and year (raw daily files), or
#   'shaded':  MEAN_RADIATION_INCOMING_SHADING_PERIOD of the shaded run itself (previous behaviour)
RAD_SOURCE = 'control'
RAW_DAILY_DIR = Path(cfg.SHADING_RAW_DATA_PARQUET_DIR)   # one parquet file per simulation, daily rows
RAW_RADN_COL = 'WEATHER_RADN'                          # daily radiation column after formatting
WINDOW_DAYS = 14                                       # expected days per shading window
VERBOSE_RAW = False                                    # True = print every raw file as it is processed
# Copy of the daily control radiation, saved so Figure 1 can be remade without the raw files.
# Raw files found  -> radiation read from them and this file (over)written.
# Raw files absent -> radiation read from this file.
CONTROL_RAD_FILE = Path(cfg.ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR) / f'control_daily_radiation_{CULTIVAR}.parquet'
SAVE_CONTROL_RAD = True        # False = never overwrite CONTROL_RAD_FILE

SHIFT_COL = pf.X_COL           # thermal time from anthesis to the middle of the window
ALPHA = pf.ALPHA
MIN_YEARS = pf.MIN_YEARS

# Smallest reduction (%) that counts as biologically meaningful. The sensitive period is
# reported for (a) any supported reduction and (b) a reduction larger than MIN_EFFECT_PCT.
MIN_EFFECT_PCT = 0

# Mixed-effects model
SPLINE_DF_CANDIDATES = range(4, 31)
CI_LEVEL = pf.CI_LEVEL
GRID_N = 400
N_SIM = 10_000
N_BOOT = 1_000
RANDOM_SEED = 42
N_BOOT_POINTS = 2000                   # bootstrap resamples of Fischer points (RMSE CI)
SHIFT_GRID = np.arange(-400, 401, 5)   # timing shifts tried when aligning APSIM with Fischer (°Cd)

# Figure layout
N_COLS = 2
SITE_PANEL_MM = 62
LEGEND_MM = 36                 # space reserved below the panels for the legend
X_MAJOR, X_MINOR = 500, 100    # °Cd tick spacing (labelled, unlabelled)
MS_SMALL, MS_MAIN = pf.RAW_SIZE, 6.0
GRAIN_YMIN, GRAIN_TICK_MIN = 65, 70    # 65-70 strip holds the sensitive-period bar
SHOW_SENSITIVE_BAR = False             # True = draw the black sensitive-period bar at the bottom of each panel
ROW_GAP = 0.22                 # vertical gap between rows of site panels (fraction of a panel's height); was 0.35

#SHOW_STAGES = False                    # True = draw the growth-stage lines and labels (and their legend)
SHOW_STAGES = True                     # True = draw the growth-stage lines and labels (and their legend)
STAGES_SHOWN = ['ANTHESIS_STAGE']      # which stages to draw; None = pf.STAGES_TO_SHOW (all of them)
LABEL_STAGES = False                       # True = label the stages on the right-hand side of the panel  
RAD_YLIM = (5, 30)             # radiation axis limits (MJ m-2 d-1); None = automatic
RAD_TICKS = [5, 15, 25]        # radiation axis tick values; None = automatic (about 3 ticks)
GN_COLOR = pf.var_color(RESPONSE)      # APSIM grain number (same colour as every figure)
RAD_COLOR = '#FF8D28'
TREND_COLOR = '#A9A9A9'
BAND_COLOR = '#FF8D28'                 # simultaneous confidence band

def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    p.add_argument('--quick', action='store_true',
                   help='fewer spline candidates and simulations (for checking the script runs)')
    return p.parse_args()


# ══════════════════════════ 2. FISCHER DATA ══════════════════════════
def load_digitised(file_name):
    df = pd.read_csv(FISCHER_DIR / file_name)
    df['DAYS_AFTER_SOWING'] = df['DAYS_AFTER_SOWING'].round(0).astype('int64')
    dup = df.loc[df['DAYS_AFTER_SOWING'].duplicated(), 'DAYS_AFTER_SOWING'].tolist()
    if dup:
        raise ValueError(f'{file_name}: several points round to the same day {dup}. Check the digitised values.')
    return df


def merge_on_das(base, extra):
    return (base.merge(extra, left_on='DAS', right_on='DAYS_AFTER_SOWING', how='left', validate='one_to_one')
                .drop(columns='DAYS_AFTER_SOWING'))


def load_fischer():
    weather = pd.read_csv(FISCHER_DIR / FISCHER_WEATHER_FILE)
    rows = weather.loc[weather['DAS'] == FISCHER_ANTHESIS_DAS, 'ACCUMULATED_TEMP']
    if len(rows) != 1:
        raise ValueError(f'Expected one weather row for DAS {FISCHER_ANTHESIS_DAS}, found {len(rows)}')
    anth_gdd = rows.iloc[0]
    f = merge_on_das(merge_on_das(weather, load_digitised(FISCHER_GRAIN_FILE)), load_digitised(FISCHER_RADIATION_FILE))
    f['DEGREE_DAYS_FROM_ANTHESIS'] = f['ACCUMULATED_TEMP'] - anth_gdd
    f['DAYS_FROM_ANTHESIS'] = f['DAS'] - FISCHER_ANTHESIS_DAS
    grain = f.dropna(subset=['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'])
    rad = f.dropna(subset=['SOLAR_RADATION'])
    trend = load_digitised(FISCHER_TREND_FILE)[['DAYS_AFTER_SOWING', 'GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL']]
    trend = merge_on_das(weather[['DAS', 'ACCUMULATED_TEMP']], trend).dropna(subset=['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'])
    trend['DEGREE_DAYS_FROM_ANTHESIS'] = trend['ACCUMULATED_TEMP'] - anth_gdd
    trend = trend.sort_values('DEGREE_DAYS_FROM_ANTHESIS')
    print(f'Fischer: {len(grain)} grain-number points, {len(rad)} radiation points, '
          f'{len(trend)} trend-line points. Anthesis = {anth_gdd:.0f} °Cd after sowing.')
    return grain, rad, trend


# ══════════════════════════ 3. APSIM DATA ══════════════════════════
APSIM_COLUMNS = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR', 'SHIFT_DOY', 'DOY_ANTHESIS_STAGE', 'DOY_MATURITY',
                 RESPONSE, 'START_SHADING_DOY', 'END_SHADING_DOY', pf.DD_ANTHESIS_COL,
                 'CUM_DEGREE_DAY_MID_SHADING', 'CUM_DEGREE_DAY_START_SHADING', 'CUM_DEGREE_DAY_END_SHADING',
                 'MEAN_RADIATION_INCOMING_SHADING_PERIOD']


def load_apsim():
    print(f'APSIM data: {APSIM_FILE}' + ('  (limited file)' if APSIM_FILE == APSIM_FILE_LIMITED else ''))
    df = pf.load_parquet(APSIM_FILE, APSIM_COLUMNS, filters={'CULTIVAR': CULTIVAR}, optional=pf.stage_columns())
    # Same rule as every other figure: drop shading windows that end after maturity
    df = pf.drop_after_maturity(df, end_col='END_SHADING_DOY', maturity_col='DOY_MATURITY')
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, [RESPONSE]))
    shaded['DAYS_FROM_ANTHESIS_MID_SHADING'] = shaded['SHIFT_DOY'] - shaded['DOY_ANTHESIS_STAGE']
    shaded['DAYS_FROM_ANTHESIS_START_SHADING'] = shaded['START_SHADING_DOY'] - shaded['DOY_ANTHESIS_STAGE']
    shaded['DAYS_FROM_ANTHESIS_END_SHADING'] = shaded['END_SHADING_DOY'] - shaded['DOY_ANTHESIS_STAGE']
    shaded['GDD_FROM_ANTHESIS_START_SHADING'] = shaded['CUM_DEGREE_DAY_START_SHADING'] - shaded[pf.DD_ANTHESIS_COL]
    shaded['GDD_FROM_ANTHESIS_END_SHADING'] = shaded['CUM_DEGREE_DAY_END_SHADING'] - shaded[pf.DD_ANTHESIS_COL]
    shaded = shaded.dropna(subset=[SHIFT_COL, RESPONSE])
    shaded['SHIFT_BIN'] = pf.dd_bin(shaded[SHIFT_COL])
    if RAD_SOURCE == 'control':
        shaded[RAD_COL] = control_window_radiation(shaded, get_control_daily())
        both = shaded[[RAD_COL, 'MEAN_RADIATION_INCOMING_SHADING_PERIOD']].dropna()
        print(f'Radiation over the shading windows (MJ m-2 d-1): control mean {both[RAD_COL].mean():.2f}, '
              f'shaded-run mean {both["MEAN_RADIATION_INCOMING_SHADING_PERIOD"].mean():.2f}')
    else:
        shaded[RAD_COL] = shaded['MEAN_RADIATION_INCOMING_SHADING_PERIOD']
    sites = [s for s in pf.site_order if s in set(shaded['SITE'])]
    others = sorted(set(shaded['SITE']) - set(pf.site_order))
    if others:
        print(f'Sites not in pf.site_order (not plotted): {others}')
    print(f'{CULTIVAR}: {len(sites)} sites {sites}')
    stages = pf.stage_summary(df, ['SITE', 'CULTIVAR'])
    return df, shaded[shaded['SITE'].isin(sites)], sites, stages


RAD_COL = 'RADIATION_SHADING_WINDOW'      # radiation column used in the figures and tables

# Raw APSIM output: SIM_FILE = site_year_variable_shift_percentchange_doy_cultivar
SIM_PATTERN = re.compile(r'^([^_]+)_(\d{4})_([^_]+)_([^_]+)_([^_]+)_([^_]+)_([^_]+)$')
SIM_COLS = ['SITE', 'YEAR', 'VARIABLE', 'SHIFT', 'PERCENTCHANGE', 'SHIFT_DOY', 'CULTIVAR']


def format_raw(df):
    """Column names, experimental variables from SIM_FILE, and DOY_CONT, as in the processing scripts."""
    ###########COLUMN NAME FORMATTING###########
    df.columns = [col.upper() for col in df.columns]
    df.columns = df.columns.str.replace('.', '_', regex=False)
    df = df.rename(columns={'CLOCK_TODAY': 'DATE'})

    ###########EXTRACT EXPERIMENTAL VARIABLES FROM SIM FILE/APSIM FILE NAME###########
    extracted = df['SIM_FILE'].astype(str).str.extract(SIM_PATTERN)
    extracted.columns = SIM_COLS
    bad = extracted.isna().all(axis=1)
    if bad.any():
        for f in df.loc[bad, 'SIM_FILE'].unique():
            print(f"Error: filename doesn't match "
                  f"'site_year_variable_shift_percentchange_doy_cultivar.apsimx': {f}")
        raise ValueError(f'{bad.sum()} row(s) have an invalid SIM_FILE name')
    if VERBOSE_RAW:
        for _, row in extracted.assign(SIM_FILE=df['SIM_FILE']).drop_duplicates('SIM_FILE').iterrows():
            print(f"Processing {row['SIM_FILE']} - site: {row['SITE']}, year: {row['YEAR']}, "
                  f"variable: {row['VARIABLE']}, shift: {row['SHIFT']}, "
                  f"percentchange: {row['PERCENTCHANGE']}, doy: {row['SHIFT_DOY']}, "
                  f"cultivar: {row['CULTIVAR']}")
    df[SIM_COLS] = extracted
    for c in ['YEAR', 'SHIFT_DOY', 'PERCENTCHANGE']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    ###########DEALING_WITH_DATES###########
    df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
    df['YEAR_DATE'] = df['DATE'].dt.year
    df['DOY'] = df['DATE'].dt.dayofyear
    # DOY continues into the next year (+365, +1 if the experiment's first year is a leap year)
    df['DOY_CONT'] = np.where(
        df['YEAR_DATE'] > df['YEAR'],
        df['DOY'] + 365 + pd.to_datetime(df['YEAR'].astype(int).astype(str)).dt.is_leap_year,
        df['DOY'])
    return df


def load_control_daily():
    """Daily SITE, YEAR, DOY_CONT and radiation from the raw CONTROL runs of CULTIVAR."""
    files = sorted(RAW_DAILY_DIR.glob(f'*_control_*_{CULTIVAR}.parquet'))
    if not files:
        raise FileNotFoundError(f'No control files *_control_*_{CULTIVAR}.parquet in {RAW_DAILY_DIR}')
    wanted = {'SIM_FILE', 'CLOCK_TODAY', 'DATE', RAW_RADN_COL}
    frames = []
    for f in files:
        names = pq.read_schema(f).names              # read only the columns needed (any case, '.' or '_')
        cols = [n for n in names if n.upper().replace('.', '_') in wanted]
        df = pq.read_table(f, columns=cols).to_pandas()
        if 'SIM_FILE' not in [c.upper() for c in df.columns]:
            df['SIM_FILE'] = f.stem                  # fall back to the file name
        df = format_raw(df)
        df = df[(df['VARIABLE'] == pf.CONTROL_LABEL) & (df['CULTIVAR'] == CULTIVAR)]
        frames.append(df[['SITE', 'YEAR', 'DOY_CONT', RAW_RADN_COL]])
    daily = pd.concat(frames, ignore_index=True).dropna()
    daily['YEAR'] = daily['YEAR'].astype(int)
    dup = daily.duplicated(['SITE', 'YEAR', 'DOY_CONT'])
    if dup.any():
        raise ValueError(f'{dup.sum()} duplicated control days (more than one control run per site-year?)')
    print(f'Control radiation: {len(files)} raw control files, '
          f'{daily.groupby(["SITE", "YEAR"]).ngroups} site-years, {len(daily)} days')
    return daily

def get_control_daily():
    """Daily control radiation: from the raw files if present (and saved to CONTROL_RAD_FILE),
    otherwise from CONTROL_RAD_FILE."""
    raw_found = RAW_DAILY_DIR.is_dir() and any(RAW_DAILY_DIR.glob(f'*_control_*_{CULTIVAR}.parquet'))
    if raw_found:
        print(f'Control radiation: reading raw daily files in {RAW_DAILY_DIR}')
        daily = load_control_daily()
        if SAVE_CONTROL_RAD:
            CONTROL_RAD_FILE.parent.mkdir(parents=True, exist_ok=True)
            daily.to_parquet(CONTROL_RAD_FILE, index=False)
            print(f'Control radiation: saved {len(daily)} days to {CONTROL_RAD_FILE}')
        return daily
    if CONTROL_RAD_FILE.is_file():
        print(f'Control radiation: raw files not found, using the saved file {CONTROL_RAD_FILE}')
        daily = pd.read_parquet(CONTROL_RAD_FILE)
        print(f'Control radiation: {daily.groupby(["SITE", "YEAR"]).ngroups} site-years, {len(daily)} days')
        return daily
    raise FileNotFoundError(f'No control radiation: no raw files *_control_*_{CULTIVAR}.parquet in '
                            f'{RAW_DAILY_DIR}, and no saved file {CONTROL_RAD_FILE}. '
                            "Set RAD_SOURCE = 'shaded' to use the shaded runs' radiation instead.")

def control_window_radiation(shaded, daily):
    """Mean daily control radiation over each shaded run's window, START_SHADING_DOY to
    END_SHADING_DOY inclusive (DOY_CONT), from the control run of the same site and year."""
    out = np.full(len(shaded), np.nan)
    n_days = np.zeros(len(shaded), dtype=int)
    start = shaded['START_SHADING_DOY'].to_numpy(dtype=float)
    end = shaded['END_SHADING_DOY'].to_numpy(dtype=float)
    groups = {k: g.sort_values('DOY_CONT') for k, g in daily.groupby(['SITE', 'YEAR'])}
    keys = pd.DataFrame({'SITE': shaded['SITE'].to_numpy(), 'YEAR': shaded['YEAR'].astype(int).to_numpy()})
    for k, idx in keys.groupby(['SITE', 'YEAR']).indices.items():
        g = groups.get(k)
        if g is None:
            continue
        doy = g['DOY_CONT'].to_numpy(dtype=float)
        csum = np.concatenate([[0.0], np.cumsum(g[RAW_RADN_COL].to_numpy(dtype=float))])
        lo = np.searchsorted(doy, start[idx], side='left')
        hi = np.searchsorted(doy, end[idx], side='right')
        n = hi - lo
        n_days[idx] = n
        out[idx] = np.where(n > 0, (csum[hi] - csum[lo]) / np.maximum(n, 1), np.nan)
    missing = int(np.isnan(out).sum())
    short = int(((n_days > 0) & (n_days != WINDOW_DAYS)).sum())
    if missing:
        print(f'WARNING: {missing} shaded runs have no matching control days (radiation set to NaN)')
    if short:
        print(f'WARNING: {short} shading windows have a number of control days other than {WINDOW_DAYS} '
              f'(e.g. the window runs past the end of the control run); their mean uses the days available')
    return out


# ══════════════════════════ 4. PAIRED TESTS ══════════════════════════
def one_sided_threshold(pct):
    """One-sided test that the mean % change is below -MIN_EFFECT_PCT (t-test and Wilcoxon)."""
    x = np.asarray(pct, float) - 100 + MIN_EFFECT_PCT
    if len(x) < MIN_YEARS:
        return np.nan, np.nan, np.nan
    if np.ptp(x) < 1e-9:
        t_p = 1.0 if abs(x.mean()) < 1e-9 or x.mean() > 0 else 0.0
        return t_p, t_p, True
    t_p = stats.ttest_1samp(x, 0.0, alternative='less').pvalue
    try:
        w_p = stats.wilcoxon(x[np.abs(x) > pf.ZERO_TOL], alternative='less').pvalue
    except ValueError:
        w_p = np.nan
    return t_p, w_p, stats.shapiro(x).pvalue >= ALPHA if len(x) >= 3 else False


def paired_tests(shaded):
    """Bin summary and both tests from pf, plus the extra columns Figure 1 needs."""
    per_year = pf.bin_per_year(shaded, [pf.pct_col(RESPONSE)], ['SITE'])
    s = pf.bin_summary(per_year, ['SITE']).rename(columns={'DD_BIN': 'SHIFT_BIN'})
    # one row per SITE x YEAR x BIN, for the mixed model and the year-by-year Fischer comparison
    paired = (shaded.groupby(['SITE', 'YEAR', 'SHIFT_BIN'], as_index=False)
                    .agg(shaded=(RESPONSE, 'mean'), control=(f'CONTROL_{RESPONSE}', 'first'),
                         pct=(pf.pct_col(RESPONSE), 'mean'), mean_shift=(SHIFT_COL, 'mean'),
                         mean_days=('DAYS_FROM_ANTHESIS_MID_SHADING', 'mean'),
                         radiation=(RAD_COL, 'mean')))
    paired['pct_diff'] = paired['pct'] - 100
    extra = paired.groupby(['SITE', 'SHIFT_BIN'], as_index=False).agg(
        mean_days_from_anthesis=('mean_days', 'mean'), mean_radiation=('radiation', 'mean'))
    s = s.merge(extra, on=['SITE', 'SHIFT_BIN'], how='left')
    s['mean_shift_in_bin'] = s['X_MEAN']
    s['n_years'] = s['N_YEARS']
    s['mean_pct_diff'] = s['MEAN'] - 100
    s['pct_ci_low'], s['pct_ci_high'] = s['CI_LOW'] - 100, s['CI_HIGH'] - 100
    s['bin_lower'] = s['SHIFT_BIN'] - pf.DD_BIN_WIDTH / 2
    s['bin_upper'] = s['SHIFT_BIN'] + pf.DD_BIN_WIDTH / 2
    # threshold test (reduction larger than MIN_EFFECT_PCT), Holm within site
    thr = [one_sided_threshold(g['PCT']) for _, g in per_year.groupby(['SITE', 'DD_BIN'], sort=True)]
    s[['thr_t_p', 'thr_wilcoxon_p', 'pct_normal']] = pd.DataFrame(thr, index=s.index)
    for col in ['thr_t_p', 'thr_wilcoxon_p']:
        s[col + '_holm'] = s.groupby('SITE')[col].transform(pf._holm)
    s['significant_unadjusted'] = s['T_P'] <= ALPHA
    for test in pf.TESTS:
        T = test.upper()
        sig = s[f'STATS_{T}'] == 'Significant'
        s[f'significant_{test}'] = sig
        s[f'significant_reduction_{test}'] = sig & (s['mean_pct_diff'] < 0)
        if test == 'ttest':
            p_thr = np.where(s['pct_normal'] == True, s['thr_t_p_holm'], s['thr_wilcoxon_p_holm'])
        else:
            p_thr = s['thr_wilcoxon_p_holm'].to_numpy()
        s[f'sensitive_{test}'] = sig & (p_thr <= ALPHA)
    return per_year, s, paired


# ══════════════════════════ 5. MIXED MODEL ══════════════════════════
OPTIMISERS = ['powell', 'nm', 'bfgs', 'lbfgs']


def fit_mixed(formula, data, reml):
    """Linear mixed model with a random intercept for YEAR; several optimisers, best valid fit kept."""
    model = smf.mixedlm(formula, data, groups=data['YEAR'])
    fits = []
    for method in OPTIMISERS:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            try:
                res = model.fit(reml=reml, method=method, maxiter=2000)
            except Exception:
                continue
        if np.isfinite(res.llf) and res.scale > 0:
            fits.append(res)
    if not fits:
        raise RuntimeError(f'No optimiser produced a valid fit for: {formula}')
    return max(fits, key=lambda r: (bool(r.converged), r.llf))


def contiguous_runs(mask):
    runs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def main_run(mask, effect):
    """The run containing the largest reduction (else the longest): (start, end, number of runs)."""
    mask = np.asarray(mask, dtype=bool)
    runs = contiguous_runs(mask)
    if not runs:
        return None, None, 0
    i_min = int(np.nanargmin(np.where(mask, effect, np.nan)))
    chosen = next((r for r in runs if r[0] <= i_min <= r[1]), max(runs, key=lambda r: r[1] - r[0]))
    return chosen[0], chosen[1], len(runs)


def mixed_models(paired, rng):
    mixed_rows, curve_frames, year_frames = [], [], []
    for site, d in paired.groupby('SITE'):
        d = d.rename(columns={'mean_shift': 'shift'}).dropna(subset=['shift', 'pct_diff']).reset_index(drop=True)
        lo, hi = d['shift'].min(), d['shift'].max()

        def spline(k):
            return f'bs(shift, df={k}, degree=3, lower_bound={lo}, upper_bound={hi})'

        ml_fits = {k: fit_mixed(f'pct_diff ~ {spline(k)}', d, reml=False) for k in SPLINE_DF_CANDIDATES}
        best_k = min(ml_fits, key=lambda k: ml_fits[k].aic)
        if best_k == max(SPLINE_DF_CANDIDATES):
            print(f'NOTE ({site}): best spline df is the largest tried ({best_k}); consider widening the range.')
        null = fit_mixed('pct_diff ~ 1', d, reml=False)
        lr_stat = 2 * (ml_fits[best_k].llf - null.llf)
        lr_p = stats.chi2.sf(lr_stat, df=best_k)

        final = fit_mixed(f'pct_diff ~ {spline(best_k)}', d, reml=True)
        var_year, var_resid = float(final.cov_re.iloc[0, 0]), float(final.scale)
        year_frames.append(pd.DataFrame({'SITE': site, 'YEAR': list(final.random_effects.keys()),
                                         'year_offset_pct': [float(v.iloc[0]) for v in final.random_effects.values()]}))

        grid = np.linspace(lo, hi, GRID_N)
        X_data = dmatrix('1 + ' + spline(best_k), d, return_type='dataframe')
        X_grid = np.asarray(build_design_matrices([X_data.design_info], pd.DataFrame({'shift': grid}))[0])
        beta = final.fe_params[X_data.columns].to_numpy()
        V = final.cov_params().loc[X_data.columns, X_data.columns].to_numpy()
        fitted = X_grid @ beta
        se = np.sqrt(np.einsum('ij,jk,ik->i', X_grid, V, X_grid))
        z = stats.norm.ppf(0.5 + CI_LEVEL / 2)
        pw_lo, pw_hi = fitted - z * se, fitted + z * se
        sims = rng.multivariate_normal(np.zeros(len(beta)), V, size=N_SIM)
        crit_sim = np.quantile(np.abs((X_grid @ sims.T) / se[:, None]).max(axis=0), CI_LEVEL)
        sim_lo, sim_hi = fitted - crit_sim * se, fitted + crit_sim * se

        X_rows, y = X_data.to_numpy(), d['pct_diff'].to_numpy()
        years = d['YEAR'].unique()
        rows_by_year = [np.flatnonzero(d['YEAR'].to_numpy() == yr) for yr in years]
        boot = np.empty((N_BOOT, GRID_N))
        for b in range(N_BOOT):
            idx = np.concatenate([rows_by_year[i] for i in rng.integers(0, len(years), len(years))])
            b_beta, *_ = np.linalg.lstsq(X_rows[idx], y[idx], rcond=None)
            boot[b] = X_grid @ b_beta
        b_sd = boot.std(axis=0, ddof=1)
        crit_boot = np.quantile(np.abs((boot - boot.mean(axis=0)) / b_sd).max(axis=1), CI_LEVEL)
        boot_lo, boot_hi = fitted - crit_boot * b_sd, fitted + crit_boot * b_sd

        row = {'SITE': site, 'n_years': len(years), 'n_obs': len(d), 'spline_df': best_k,
               'converged': final.converged, 'LRT_chi2': lr_stat, 'LRT_df': best_k, 'LRT_p': lr_p,
               'max_reduction_pct': fitted.min(), 'timing_of_max_reduction': grid[np.argmin(fitted)],
               'var_year': var_year, 'sd_year': np.sqrt(var_year), 'var_resid': var_resid,
               'ICC_year': var_year / (var_year + var_resid)}
        for band, upper in [('pointwise', pw_hi), ('simultaneous', sim_hi), ('bootstrap', boot_hi)]:
            for tag, threshold in [('any', 0.0), ('min_effect', -MIN_EFFECT_PCT)]:
                i0, i1, n_runs = main_run(upper < threshold, fitted)
                row[f'onset_{band}_{tag}'] = grid[i0] if i0 is not None else np.nan
                row[f'end_{band}_{tag}'] = grid[i1] if i1 is not None else np.nan
                row[f'n_runs_{band}_{tag}'] = n_runs
        mixed_rows.append(row)
        curve_frames.append(pd.DataFrame({'SITE': site, 'shift': grid, 'fitted_pct': fitted,
                                          'pointwise_lo': pw_lo, 'pointwise_hi': pw_hi,
                                          'simultaneous_lo': sim_lo, 'simultaneous_hi': sim_hi,
                                          'bootstrap_lo': boot_lo, 'bootstrap_hi': boot_hi}))
        print(f'  mixed model {site}: spline df {best_k}, LRT p = {lr_p:.3g}')
    return pd.DataFrame(mixed_rows), pd.concat(curve_frames, ignore_index=True), pd.concat(year_frames, ignore_index=True)


# ══════════════════════════ 6. SENSITIVE PERIOD ══════════════════════════
def sensitive_periods(s_all, mixed_summary, shaded, sites):
    def gdd_to_days(site, gdd):
        if not np.isfinite(gdd):
            return np.nan
        s = s_all[s_all['SITE'] == site].dropna(subset=['mean_days_from_anthesis'])
        return float(np.interp(gdd, s['mean_shift_in_bin'], s['mean_days_from_anthesis']))

    rows = []
    for site in sites:
        s = s_all[s_all['SITE'] == site].reset_index(drop=True)
        m = mixed_summary[mixed_summary['SITE'] == site].iloc[0]
        methods = [('Paired t-test, unadjusted, any reduction', s['significant_unadjusted'] & (s['mean_pct_diff'] < 0))]
        for test in pf.TESTS:
            methods += [(f'{pf.TEST_SHORT[test]}, Holm, any reduction', s[f'significant_reduction_{test}']),
                        (f'{pf.TEST_SHORT[test]}, Holm, reduction > {MIN_EFFECT_PCT:g}%', s[f'sensitive_{test}'])]
        for label, mask in methods:
            i0, i1, n_runs = main_run(mask, s['mean_pct_diff'].to_numpy())
            rows.append({'SITE': site, 'method': label,
                         'onset_gdd': s.loc[i0, 'bin_lower'] if i0 is not None else np.nan,
                         'end_gdd': s.loc[i1, 'bin_upper'] if i1 is not None else np.nan, 'n_runs': n_runs})
        for band, band_label in [('simultaneous', 'simultaneous band'), ('bootstrap', 'year-bootstrap band')]:
            for tag, tag_label in [('any', 'any reduction'), ('min_effect', f'reduction > {MIN_EFFECT_PCT:g}%')]:
                rows.append({'SITE': site, 'method': f'Mixed model, {band_label}, {tag_label}',
                             'onset_gdd': m[f'onset_{band}_{tag}'], 'end_gdd': m[f'end_{band}_{tag}'],
                             'n_runs': m[f'n_runs_{band}_{tag}']})
    sp = pd.DataFrame(rows)
    sp['onset_days'] = [gdd_to_days(a, g) for a, g in zip(sp['SITE'], sp['onset_gdd'])]
    sp['end_days'] = [gdd_to_days(a, g) for a, g in zip(sp['SITE'], sp['end_gdd'])]

    edges = (shaded.groupby(['SITE', 'SHIFT_BIN'], as_index=False)
                   .agg(start_days=('DAYS_FROM_ANTHESIS_START_SHADING', 'mean'),
                        end_days=('DAYS_FROM_ANTHESIS_END_SHADING', 'mean'),
                        start_gdd=('GDD_FROM_ANTHESIS_START_SHADING', 'mean'),
                        end_gdd=('GDD_FROM_ANTHESIS_END_SHADING', 'mean')))

    def window_edge(site, gdd, col):
        if not np.isfinite(gdd):
            return np.nan
        r = edges[(edges['SITE'] == site) & (edges['SHIFT_BIN'] == pf.dd_bin(gdd))]
        return r[col].iloc[0] if len(r) else np.nan

    sp['span_start_days'] = [window_edge(a, g, 'start_days') for a, g in zip(sp['SITE'], sp['onset_gdd'])]
    sp['span_end_days'] = [window_edge(a, g - 1e-6, 'end_days') for a, g in zip(sp['SITE'], sp['end_gdd'])]
    sp['span_start_gdd'] = [window_edge(a, g, 'start_gdd') for a, g in zip(sp['SITE'], sp['onset_gdd'])]
    sp['span_end_gdd'] = [window_edge(a, g - 1e-6, 'end_gdd') for a, g in zip(sp['SITE'], sp['end_gdd'])]
    return sp


# ══════════════════════════ 7. FISCHER AGREEMENT ══════════════════════════
def agreement(obs, pred, rng_f, with_ci=True):
    obs, pred = np.asarray(obs, dtype=float), np.asarray(pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[ok], pred[ok]
    n = len(obs)
    out = {'n_points': n}
    if n < 3:
        return out
    d = pred - obs
    mse = np.mean(d ** 2)
    out.update({'bias': d.mean(), 'relative_bias_pct': 100 * d.mean() / obs.mean(), 'MAE': np.abs(d).mean(),
                'RMSE': np.sqrt(mse), 'nRMSE_mean_pct': 100 * np.sqrt(mse) / obs.mean(),
                'nRMSE_range_pct': 100 * np.sqrt(mse) / np.ptp(obs) if np.ptp(obs) > 0 else np.nan})
    if np.ptp(pred) > 0:
        lr = stats.linregress(pred, obs)
        tc = stats.t.ppf(0.975, n - 2)
        out.update({'slope': lr.slope, 'slope_ci_low': lr.slope - tc * lr.stderr,
                    'slope_ci_high': lr.slope + tc * lr.stderr, 'intercept': lr.intercept,
                    'intercept_ci_low': lr.intercept - tc * lr.intercept_stderr,
                    'intercept_ci_high': lr.intercept + tc * lr.intercept_stderr,
                    'r': lr.rvalue, 'r2': lr.rvalue ** 2})
    sd_p, sd_o = pred.std(), obs.std()
    if sd_p > 0 and sd_o > 0 and mse > 0:
        r = np.corrcoef(pred, obs)[0, 1]
        out.update({'SB_share_pct': 100 * d.mean() ** 2 / mse, 'SDSD_share_pct': 100 * (sd_p - sd_o) ** 2 / mse,
                    'LCS_share_pct': 100 * 2 * sd_p * sd_o * (1 - r) / mse})
    if with_ci:
        tc = stats.t.ppf(0.975, n - 1)              # t interval with n - 1 df
        se = d.std(ddof=1) / np.sqrt(n)
        out['bias_ci_low'], out['bias_ci_high'] = d.mean() - tc * se, d.mean() + tc * se
        idx = rng_f.integers(0, n, size=(N_BOOT_POINTS, n))
        out['RMSE_ci_low'], out['RMSE_ci_high'] = np.percentile(np.sqrt((d[idx] ** 2).mean(axis=1)), [2.5, 97.5])
    return out


def largest_reduction(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if not np.isfinite(y).any():
        return np.nan, np.nan
    i = int(np.nanargmin(y))
    return 100 - y[i], x[i]


def interp_sorted(x_new, x, y, hold_edges=False):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    order = np.argsort(x[ok])
    xs, ys = x[ok][order], y[ok][order]
    return np.interp(x_new, xs, ys) if hold_edges else np.interp(x_new, xs, ys, left=np.nan, right=np.nan)


def best_shift(x_obs, obs, x_pred, pred):
    """Timing shift (°Cd) with the highest correlation between Fischer and shifted APSIM.
    Positive = APSIM's response occurs that many °Cd EARLIER than Fischer's."""
    best_d, best_r, best_p = np.nan, -np.inf, None
    for dlt in SHIFT_GRID:
        p = interp_sorted(x_obs - dlt, x_pred, pred, hold_edges=True)
        if np.ptp(p) == 0:
            continue
        r = np.corrcoef(p, obs)[0, 1]
        if r > best_r:
            best_d, best_r, best_p = dlt, r, p
    if np.isfinite(best_d) and best_d in (SHIFT_GRID[0], SHIFT_GRID[-1]):
        print(f'NOTE: best shift is at the edge of SHIFT_GRID ({best_d} °Cd); consider widening it.')
    return best_d, best_p


def fischer_agreement(fischer_grain, s_all, curves, paired, sites):
    rng_f = np.random.default_rng(RANDOM_SEED)
    fobs = (fischer_grain.rename(columns={'DEGREE_DAYS_FROM_ANTHESIS': 'gdd', 'GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL': 'obs',
                                          'STATS': 'fischer_stats'})
            [['DAS', 'DAYS_FROM_ANTHESIS', 'gdd', 'obs', 'fischer_stats']].sort_values('gdd').reset_index(drop=True))
    fobs['point_id'] = np.arange(len(fobs))
    fobs['SHIFT_BIN'] = pf.dd_bin(fobs['gdd'])

    match, match_year = [], []
    for site in sites:
        bins = (s_all[s_all['SITE'] == site].set_index('SHIFT_BIN')
                [['n_years', 'mean_shift_in_bin', 'mean_pct_diff', 'pct_ci_low', 'pct_ci_high',
                  'STATS_TTEST', 'STATS_WILCOXON']])
        m = fobs.join(bins, on='SHIFT_BIN')
        m.insert(0, 'SITE', site)
        m['apsim_bin'] = 100 + m['mean_pct_diff']
        m['apsim_bin_ci_low'] = 100 + m['pct_ci_low']
        m['apsim_bin_ci_high'] = 100 + m['pct_ci_high']
        m['bin_timing_offset'] = m['gdd'] - m['mean_shift_in_bin']
        c = curves[curves['SITE'] == site]
        for out_col, in_col in [('apsim_curve', 'fitted_pct'), ('apsim_curve_ci_low', 'pointwise_lo'),
                                ('apsim_curve_ci_high', 'pointwise_hi')]:
            m[out_col] = 100 + np.interp(m['gdd'], c['shift'], c[in_col], left=np.nan, right=np.nan)
        match.append(m.drop(columns=['mean_pct_diff', 'pct_ci_low', 'pct_ci_high']))
        py = paired.loc[paired['SITE'] == site, ['YEAR', 'SHIFT_BIN', 'pct_diff']]
        y = fobs.merge(py, on='SHIFT_BIN', how='inner')
        y.insert(0, 'SITE', site)
        y['apsim_year'] = 100 + y['pct_diff']
        match_year.append(y.drop(columns='pct_diff'))
    matched = pd.concat(match, ignore_index=True)
    matched_year = pd.concat(match_year, ignore_index=True)

    x_f, y_f = fobs['gdd'].to_numpy(), fobs['obs'].to_numpy()
    f_red, f_tmax = largest_reduction(x_f, y_f)
    subsets = {'All Fischer points': fobs['point_id'],
               'Fischer significant points': fobs.loc[fobs['fischer_stats'] == 'Significant', 'point_id']}
    sources = {'Bin mean across years': 'apsim_bin', 'Mixed-model curve': 'apsim_curve'}

    rows = []
    for site in sites:
        m = matched[matched['SITE'] == site]
        for source, col in sources.items():
            for subset, ids in subsets.items():
                mm = m[m['point_id'].isin(ids)]
                rows.append({'SITE': site, 'apsim_source': source, 'fischer_points': subset,
                             **agreement(mm['obs'], mm[col], rng_f)})
    agree = pd.DataFrame(rows)

    rows = []
    for site in sites:
        s = s_all[(s_all['SITE'] == site) & (s_all['n_years'] >= MIN_YEARS)]
        c = curves[curves['SITE'] == site]
        series = {'Bin mean across years': (s['mean_shift_in_bin'], 100 + s['mean_pct_diff']),
                  'Mixed-model curve': (c['shift'], 100 + c['fitted_pct'])}
        for source, (xp, yp) in series.items():
            red, tmax = largest_reduction(xp, yp)
            shift, p_shift = best_shift(x_f, y_f, xp.to_numpy(), yp.to_numpy())
            after = agreement(y_f, p_shift, rng_f, with_ci=False) if p_shift is not None else {}
            before = agreement(y_f, interp_sorted(x_f, xp, yp, hold_edges=True), rng_f, with_ci=False)
            rows.append({'SITE': site, 'apsim_source': source, 'fischer_max_reduction_pct': f_red,
                         'apsim_max_reduction_pct': red, 'max_reduction_rel_error_pct': 100 * (red - f_red) / f_red,
                         'fischer_timing_of_max': f_tmax, 'apsim_timing_of_max': tmax,
                         'timing_difference': tmax - f_tmax, 'best_shift': shift,
                         'RMSE_before_shift': before.get('RMSE'), 'r_before_shift': before.get('r'),
                         'RMSE_after_shift': after.get('RMSE'), 'bias_after_shift': after.get('bias'),
                         'slope_after_shift': after.get('slope'), 'r_after_shift': after.get('r')})
    shape = pd.DataFrame(rows)

    rows = []
    for (site, year), g in matched_year.groupby(['SITE', 'YEAR']):
        a = agreement(g['obs'], g['apsim_year'], rng_f, with_ci=False)
        yr = paired[(paired['SITE'] == site) & (paired['YEAR'] == year)].sort_values('mean_shift')
        xp, yp = yr['mean_shift'].to_numpy(), 100 + yr['pct_diff'].to_numpy()
        red, tmax = largest_reduction(xp, yp)
        shift, _ = best_shift(x_f, y_f, xp, yp)
        rows.append({'SITE': site, 'YEAR': int(year), **a, 'apsim_max_reduction_pct': red,
                     'apsim_timing_of_max': tmax, 'best_shift': shift})
    by_year = pd.DataFrame(rows)

    compare = ['bias', 'RMSE', 'slope', 'intercept', 'r', 'apsim_max_reduction_pct', 'apsim_timing_of_max', 'best_shift']
    rows = []
    for site in sites:
        ma = agree[(agree['SITE'] == site) & (agree['apsim_source'] == 'Bin mean across years') &
                   (agree['fischer_points'] == 'All Fischer points')].iloc[0]
        ms = shape[(shape['SITE'] == site) & (shape['apsim_source'] == 'Bin mean across years')].iloc[0]
        of_mean = {**ma.to_dict(), **ms.to_dict()}
        yrs = by_year[by_year['SITE'] == site]
        for metric in compare:
            v = yrs[metric].dropna() if metric in yrs else pd.Series(dtype=float)
            rows.append({'SITE': site, 'metric': metric, 'value_for_mean_of_years': of_mean.get(metric),
                         'years_mean': v.mean(), 'years_sd': v.std(), 'years_p2.5': v.quantile(0.025),
                         'years_p97.5': v.quantile(0.975), 'n_years': len(v)})
        rows.append({'SITE': site, 'metric': '% of years with reduction >= Fischer',
                     'years_mean': 100 * (yrs['apsim_max_reduction_pct'] >= f_red).mean(), 'n_years': len(yrs)})
        rows.append({'SITE': site, 'metric': '% of years with peak at or after Fischer',
                     'years_mean': 100 * (yrs['apsim_timing_of_max'] >= f_tmax).mean(), 'n_years': len(yrs)})
    year_summary = pd.DataFrame(rows)
    print(f'Fischer: largest reduction {f_red:.1f}% at {f_tmax:.0f} °Cd from anthesis')
    return matched, matched_year, agree, shape, by_year, year_summary


# ══════════════════════════ 8. FIGURES ══════════════════════════
class Fig1:
    """Grid of site panels; each = radiation axis stacked on a grain-number axis."""

    def __init__(self, data):
        self.d = data
        self.x_min, self.x_max = data['shaded'][SHIFT_COL].min(), data['shaded'][SHIFT_COL].max()
        self.bar_y = (GRAIN_YMIN + GRAIN_TICK_MIN) / 2

    def make(self):
        sites = self.d['sites']
        n = len(sites)
        n_cols = min(N_COLS, n)
        n_rows = math.ceil(n / n_cols)
        panel_mm = min(SITE_PANEL_MM, (pf.MAX_FIG_HEIGHT_MM - LEGEND_MM) / n_rows)
        if panel_mm < 40:
            print(f'WARNING: site panels are only {panel_mm:.0f} mm tall; consider N_COLS = {n_cols + 1}.')
        h_mm = panel_mm * n_rows + LEGEND_MM
        fig = plt.figure(figsize=pf.fig_size('double', height_mm=h_mm))
        outer = fig.add_gridspec(n_rows, n_cols, bottom=(LEGEND_MM + 12) / h_mm, top=1 - 6 / h_mm,
                                 left=0.105, right=0.895, hspace=ROW_GAP, wspace=0.22)
        axes, ref = [], None
        for i in range(n):
            r, c = divmod(i, n_cols)
            inner = outer[r, c].subgridspec(2, 1, hspace=0.0, height_ratios=[40, 60])
            ax_top = fig.add_subplot(inner[0], sharex=ref)
            ref = ref or ax_top
            ax_bot = fig.add_subplot(inner[1], sharex=ref)
            axes.append((ax_top, ax_bot, r, c))
        return fig, axes

    def common(self, ax_top, ax_bot, site, k):
        raw = self.d['shaded'][self.d['shaded']['SITE'] == site]
        bins = self.d['tests'][self.d['tests']['SITE'] == site]
        fg, fr, ft = self.d['fischer']
        ax_top.scatter(raw[SHIFT_COL], raw[RAD_COL], s=MS_SMALL,
                       color=pf.lighten(RAD_COLOR), linewidths=0, zorder=pf.Z_RAW, rasterized=True)
        ax_top.scatter(bins['mean_shift_in_bin'], bins['mean_radiation'], s=MS_MAIN, marker='o',
                       color=RAD_COLOR, linewidths=0, zorder=pf.Z_STAT)
        ax_top.scatter(fr['DEGREE_DAYS_FROM_ANTHESIS'], fr['SOLAR_RADATION'], s=MS_MAIN, marker='s',
                       facecolor='black', edgecolor='black', linewidth=pf.LW_THIN, zorder=pf.Z_STAT + 1)
        pf.draw_raw(ax_bot, raw[SHIFT_COL], raw[pf.pct_col(RESPONSE)], GN_COLOR)
        ax_bot.plot(ft['DEGREE_DAYS_FROM_ANTHESIS'], ft['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'],
                    color=TREND_COLOR, linewidth=pf.LW_THICK, zorder=pf.Z_CI)
        for lab, g in fg.groupby(fg['STATS'].fillna('Insufficient Data')):
            ax_bot.scatter(g['DEGREE_DAYS_FROM_ANTHESIS'], g['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'], s=MS_MAIN * 1.3,
                           marker='s', linewidths=pf.LW_THIN, zorder=pf.Z_STAT + 1,
                           **pf.stats_marker_style(lab, 'black'))
        pf.draw_control_line(ax_bot)
        ax_top.set_title(f'({pf.panel_letters[k]}) {pf.format_site_name(site)}', loc='left',
                         fontsize=pf.FONT_SIZE_TITLE, pad=2)

    def finalise(self, fig, axes):
        grain_top = max(a[1].get_ylim()[1] for a in axes)
        rad_lim = RAD_YLIM or (min(a[0].get_ylim()[0] for a in axes), max(a[0].get_ylim()[1] for a in axes))
        n_cols = max(a[3] for a in axes) + 1
        for i, (ax_top, ax_bot, r, c) in enumerate(axes):
            ax_bot.set_xlim(self.x_min, self.x_max)
            pf.format_dd_axis(ax_bot, X_MAJOR, X_MINOR)
            ax_bot.set_ylim(GRAIN_YMIN, grain_top)
            ax_bot.yaxis.set_major_locator(mpl.ticker.MultipleLocator(10))
            ticks = [t for t in ax_bot.get_yticks() if GRAIN_TICK_MIN <= t <= grain_top]
            ax_bot.set_yticks(ticks)
            ax_bot.spines['left'].set_bounds(ticks[0], ticks[-1])
            ax_bot.spines[['top', 'right']].set_visible(False)
            ax_top.set_ylim(*rad_lim)
            if RAD_TICKS is not None:
                ax_top.yaxis.set_major_locator(mpl.ticker.FixedLocator(RAD_TICKS))
            else:
                ax_top.yaxis.set_major_locator(mpl.ticker.MaxNLocator(nbins=3, steps=[1, 2, 5, 10]))
            top_ticks = [t for t in ax_top.get_yticks() if rad_lim[0] <= t <= rad_lim[1]]
            ax_top.set_yticks(top_ticks)
            ax_top.yaxis.tick_right()
            ax_top.yaxis.set_label_position('right')
            ax_top.spines['right'].set_bounds(top_ticks[0], top_ticks[-1])
            ax_top.spines[['top', 'left', 'bottom']].set_visible(False)
            ax_top.tick_params(axis='x', bottom=False, labelbottom=False)
            if c == 0:
                ax_bot.set_ylabel('Grain number\n(% of unshaded control)')
            if c == n_cols - 1 or i == len(axes) - 1:
                ax_top.set_ylabel('Radiation\n(MJ m$^{-2}$ d$^{-1}$)')
            # #Just the bottom row gets x-axis labels (and only if not sharing with a row below)    
            # if i + n_cols >= len(axes):
            #     ax_bot.set_xlabel(pf.XLABEL_DD.replace(' to middle', ' to middle\n'))
            # else:
            #     ax_bot.tick_params(axis='x', labelbottom=False)
            #All panels get x axis labels, but only the bottom row gets the extra line of text
            if i + n_cols >= len(axes):
                ax_bot.set_xlabel(pf.XLABEL_DD.replace(' to middle', ' to middle\n'))
        # growth stages last (limits are final): labels on the radiation axis, lines through both
        if not SHOW_STAGES:
            return
        for (ax_top, ax_bot, _, _), site in zip(axes, self.d['sites']):
            st = pf.stages_for(self.d['stages'], SITE=site, CULTIVAR=CULTIVAR)
            pf.draw_stages(ax_top, st, stages_to_show=STAGES_SHOWN, labels=LABEL_STAGES)
            pf.draw_stages(ax_bot, st, stages_to_show=STAGES_SHOWN, labels=False)

    def bar(self, ax, onset, end):
        if not SHOW_SENSITIVE_BAR:
            return
        if np.isfinite(onset) and np.isfinite(end):
            ax.plot([onset, end], [self.bar_y, self.bar_y], color='black', linewidth=3, solid_capstyle='butt', zorder=3)

    def legend_bar(self):
        """Legend entry for the sensitive-period bar (none when SHOW_SENSITIVE_BAR is False)."""
        if not SHOW_SENSITIVE_BAR:
            return []
        return [mlines.Line2D([], [], color='black', linewidth=3,
                              label=f'Sensitive period (reduction > {MIN_EFFECT_PCT:g}%)')]

    def legends(self, fig, groups):
        groups = [(t, h) for t, h in groups if h]     # skip empty groups (e.g. stages turned off)
        y = (LEGEND_MM - 1) * pf.MM_TO_INCH / fig.get_figheight()
        xs = np.linspace(0.13, 0.87, len(groups))
        for (title, handles), x in zip(groups, xs):
            leg = fig.legend(handles=handles, title=title, loc='upper center', bbox_to_anchor=(x, y),
                             frameon=False, fontsize=7, title_fontsize=7, handlelength=2.0,
                             handletextpad=0.5, labelspacing=0.3, alignment='left')
            leg.get_title().set_fontweight('bold')
            fig.add_artist(leg)

    def legend_data(self):
        return [pf.handle_marker(f'APSIM bin mean ± {CI_LEVEL:.0%} CI', GN_COLOR),
                pf.handle_marker('APSIM, all simulations', face=pf.lighten(GN_COLOR), edge=pf.lighten(GN_COLOR), size=2.5),
                pf.handle_marker(FISCHER_LABEL, marker='s'),
                mlines.Line2D([], [], color=TREND_COLOR, linewidth=pf.LW_THICK, label='Trend line, Fischer (1985)'),
                pf.handle_marker('Radiation: APSIM mean, Fischer', RAD_COLOR),
                mlines.Line2D([], [], label=pf.CONTROL_LINE_LABEL,
                              **{k: v for k, v in pf.CONTROL_LINE_STYLE.items() if k != 'zorder'})]

    def legend_fischer(self):
        return [pf.handle_marker(pf.STATS_LEGEND_LABELS[s].split(' (')[0], marker='s',
                                 face=pf.stats_marker_style(s, 'black')['facecolor'],
                                 edge=pf.stats_marker_style(s, 'black')['edgecolor'])
                for s in ['Significant', 'Non Significant']] + [
                pf.handle_marker('Assumptions not met', marker='s', face=pf.lighten('black', 0.6), edge='black')]

    def paired(self, test):
        fig, axes = self.make()
        used = set()
        sp = self.d['periods']
        for k, (site, (ax_top, ax_bot, _, _)) in enumerate(zip(self.d['sites'], axes)):
            self.common(ax_top, ax_bot, site, k)
            s = self.d['tests'][self.d['tests']['SITE'] == site].rename(columns={'SHIFT_BIN': 'DD_BIN'})
            used |= pf.draw_series(ax_bot, s, test, GN_COLOR, show_raw=False)
            per = sp[(sp['SITE'] == site) & (sp['method'] == f'{pf.TEST_SHORT[test]}, Holm, reduction > {MIN_EFFECT_PCT:g}%')]
            if len(per):
                self.bar(ax_bot, per['onset_gdd'].iloc[0], per['end_gdd'].iloc[0])
        self.finalise(fig, axes)
        self.legends(fig, [
            ('Data', self.legend_data()),
            (f'APSIM {pf.TEST_SHORT[test]} (Holm)', pf.handles_stats(test, used, color=GN_COLOR) + self.legend_bar()),
            ('Fischer (1985) significance', self.legend_fischer()),
                        ('Growth stage', pf.handles_stages(STAGES_SHOWN) if SHOW_STAGES else []),
        ])
        return fig

    def mixed(self):
        fig, axes = self.make()
        for k, (site, (ax_top, ax_bot, _, _)) in enumerate(zip(self.d['sites'], axes)):
            self.common(ax_top, ax_bot, site, k)
            c = self.d['curves'][self.d['curves']['SITE'] == site]
            m = self.d['mixed'][self.d['mixed']['SITE'] == site].iloc[0]
            ax_bot.fill_between(c['shift'], 100 + c['simultaneous_lo'], 100 + c['simultaneous_hi'],
                                color=BAND_COLOR, linewidth=0, zorder=pf.Z_CI)
            for col in ['bootstrap_lo', 'bootstrap_hi']:
                ax_bot.plot(c['shift'], 100 + c[col], color='black', linestyle=':', linewidth=pf.LW_THIN, zorder=pf.Z_STAT)
            ax_bot.plot(c['shift'], 100 + c['fitted_pct'], color='black', linewidth=pf.LW_THICK, zorder=pf.Z_STAT)
            self.bar(ax_bot, m['onset_simultaneous_min_effect'], m['end_simultaneous_min_effect'])
        self.finalise(fig, axes)
        self.legends(fig, [
            ('Data', self.legend_data()[1:]),
            ('APSIM mixed-effects model', [
                mlines.Line2D([], [], color='black', linewidth=pf.LW_THICK, label='Fitted curve'),
                mpatches.Patch(facecolor=BAND_COLOR, label='95% simultaneous band'),
                mlines.Line2D([], [], color='black', linestyle=':', linewidth=pf.LW_THIN, label='95% year-bootstrap band'),
            ] + self.legend_bar()),
            ('Fischer (1985) significance', self.legend_fischer()),
            ('Growth stage', pf.handles_stages() if SHOW_STAGES else []),
        ])
        return fig


# ══════════════════════════ MAIN ══════════════════════════
def main():
    global SPLINE_DF_CANDIDATES, N_SIM, N_BOOT
    args = parse_args()
    if args.quick:
        SPLINE_DF_CANDIDATES, N_SIM, N_BOOT = range(4, 9), 500, 100
        print('QUICK MODE: reduced spline candidates and simulations (do not use for the paper)')
    start = pf.start_script(__file__)
    rng = np.random.default_rng(RANDOM_SEED)

    fischer = load_fischer()
    df, shaded, sites, stages = load_apsim()
    per_year, tests, paired = paired_tests(shaded)
    print('\nMixed-effects models')
    mixed, curves, year_effects = mixed_models(paired[paired['SITE'].isin(sites)], rng)
    periods = sensitive_periods(tests, mixed, shaded, sites)
    with pd.option_context('display.width', 250, 'display.max_colwidth', 60):
        print(periods[['SITE', 'method', 'n_runs', 'onset_gdd', 'end_gdd', 'onset_days', 'end_days']].round(0).to_string(index=False))
    matched, matched_year, agree, shape, by_year, year_summary = fischer_agreement(fischer[0], tests, curves, paired, sites)

    figs = Fig1({'shaded': shaded, 'tests': tests, 'sites': sites, 'stages': stages, 'fischer': fischer,
                 'periods': periods, 'mixed': mixed, 'curves': curves})
    for test in pf.TESTS:
        pf.save(figs.paired(test), f'figure_1_all_sites_{CULTIVAR}_{test}')
    pf.save(figs.mixed(), f'figure_1_all_sites_{CULTIVAR}_mixed_model')

    tables = {
        f'figure_1_{CULTIVAR}_paired_test_results': tests,
        f'figure_1_{CULTIVAR}_per_year_bins': per_year,
        f'figure_1_{CULTIVAR}_mixed_model_summary': mixed,
        f'figure_1_{CULTIVAR}_mixed_model_curves': curves,
        f'figure_1_{CULTIVAR}_mixed_model_year_effects': year_effects,
        f'figure_1_{CULTIVAR}_sensitive_period': periods,
        f'figure_1_{CULTIVAR}_fischer_matched_points': matched,
        f'figure_1_{CULTIVAR}_fischer_matched_points_by_year': matched_year,
        f'figure_1_{CULTIVAR}_fischer_agreement': agree,
        f'figure_1_{CULTIVAR}_fischer_response_shape': shape,
        f'figure_1_{CULTIVAR}_fischer_agreement_by_year': by_year,
        f'figure_1_{CULTIVAR}_fischer_year_summary': year_summary,
        f'figure_1_{CULTIVAR}_growth_stages_dd': stages,
    }
    for name, t in tables.items():
        pf.save_table(t, name)
    print(fischer[0][['DAS', 'DAYS_FROM_ANTHESIS', 'DEGREE_DAYS_FROM_ANTHESIS',
                      'GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL', 'STATS']].to_string(index=False))
    if SHOW_STAGES:
        pf.print_stage_caption(STAGES_SHOWN)
    pf.finish_script(start)


if __name__ == '__main__':
    main()