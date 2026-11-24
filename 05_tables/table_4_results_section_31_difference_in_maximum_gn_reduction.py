"""
Results 3.1, Table 4: largest mean reduction in grain number by site (APSIM)
compared with the largest reduction in Fischer (1985) Expt 74A.

For each site, APSIM grain number at maturity in each shaded run is expressed as
% of the same-year control. Shading windows are binned by thermal time from
anthesis (window mid-point, 20 °Cd bins), averaged within year, then across
years. The bin with the lowest mean (among bins with >= MIN_YEARS years) is the
site's maximum reduction.

Difference column = Fischer Expt 74A minimum (% of unshaded control) minus the
APSIM site mean, so a negative value means APSIM's largest reduction is smaller
than Fischer's.

The final row, 'Average across all sites', gives for each numeric column the
mean ± SD across the 8 site values with a t-based 95% CI (n = number of sites).
For the degree-day column the bin centres are averaged.

Output: table_4_results_section_31_difference_in_maximum_gn_reduction_between_
expt74A_and_APSIM_all_sites.csv in cfg.SECOND_DRAFT_DIR.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# --------------------------------------------------------------------------
# Locate config_loader.py and paper_1_functions.py (one folder up)
# --------------------------------------------------------------------------
try:
    SCRIPTS_BASE = Path(__file__).resolve().parents[1]
except NameError:
    SCRIPTS_BASE = Path("$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments")

if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg            # noqa: E402
import paper_1_functions as pf           # noqa: E402

# ══════════════════════════ SETTINGS ══════════════════════════
# Fischer (1985) digitised data and weather: stored with the scripts
FISCHER_DIR = Path(cfg.ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR)

# APSIM results: the full file if it exists, otherwise the limited file for upload
APSIM_FILE_FULL = Path(cfg.ALL_DATA_SHADED_DF)
APSIM_FILE_LIMITED = Path(cfg.LIMITED_SHADED_DF)
if APSIM_FILE_FULL.is_file():
    APSIM_FILE = APSIM_FILE_FULL
    print(f'APSIM data: full file {APSIM_FILE}')
elif APSIM_FILE_LIMITED.is_file():
    APSIM_FILE = APSIM_FILE_LIMITED
    print(f'APSIM data: full file not found, using the limited file {APSIM_FILE}')
else:
    raise FileNotFoundError(f'No APSIM data file found:\n  {APSIM_FILE_FULL}\n  {APSIM_FILE_LIMITED}')

CULTIVAR = cfg.EXAMPLE_CULTIVAR
RESPONSE = 'GRAIN_NUMBER_MATURITY'
POINT = 'MID'            # shading window point: 'START', 'MID' or 'END'
BIN_WIDTH = 20.0         # °Cd
MIN_YEARS = 5            # bins with fewer years are not eligible
CI_LEVEL = 0.95

DD_SHADING = f'CUM_DEGREE_DAY_{POINT}_SHADING'
DD_ANTHESIS = 'CUM_DEGREE_DAY_ANTHESIS_STAGE'

FISCHER_WEATHER_FILE = 'fischer_1985_daily_temp_radiation.csv'   # daily weather
FISCHER_GRAIN_FILE = 'fischer_grain_number_data.csv'             # digitised Fig. 1 points
FISCHER_ANTHESIS_DAS = 86      # days after sowing to 50% anthesis (Fischer 1975, p. 610)
FISCHER_PCT_COL = 'GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'

OUTPUT_FILE = ('table_4_results_section_31_difference_in_maximum_gn_reduction_'
               'between_expt74A_and_APSIM_all_sites.csv')

COL_SITE = 'Site'
COL_MEAN = 'Mean maximum reduction in grain number (% ± SD)'
COL_CI = 'Confidence Interval of mean'
COL_DIFF = 'Difference between mean and maximum reduction in Expt74A (%)'
COL_N = 'Number of Years in Bin'
COL_DD = 'Degree Days from Anthesis (°Cd)'


def bin_centre(dd):
    return np.floor(np.round(dd / BIN_WIDTH, 9)) * BIN_WIDTH + BIN_WIDTH / 2


def t_half_width(sd, n):
    return stats.t.ppf(0.5 + CI_LEVEL / 2, n - 1) * sd / np.sqrt(n)


# ══════════════════════════ APSIM ══════════════════════════
def apsim_largest_reduction_by_site():
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR', 'SHIFT_DOY', 'END_SHADING_DOY',
            'DOY_MATURITY', DD_SHADING, DD_ANTHESIS, RESPONSE]
    df = pd.read_parquet(APSIM_FILE, columns=cols, filters=[('CULTIVAR', '==', CULTIVAR)])
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    # drop shading windows that end after maturity (control runs always kept)
    df = df[(df['VARIABLE'] == 'control') | (df['END_SHADING_DOY'] <= df['DOY_MATURITY'])]

    # % of the same-year control
    ctrl = df[(df['VARIABLE'] == 'control') & (df['SHIFT_DOY'] == 0)]
    assert not ctrl.duplicated(['SITE', 'YEAR']).any(), 'duplicate control runs'
    ctrl = ctrl[['SITE', 'YEAR', RESPONSE]].rename(columns={RESPONSE: 'CONTROL'})

    shaded = df[df['VARIABLE'] == 'radiation'].merge(
        ctrl, on=['SITE', 'YEAR'], how='inner', validate='many_to_one')
    shaded['PCT'] = 100 * shaded[RESPONSE] / shaded['CONTROL']

    # thermal time from anthesis and bin
    shaded['DD_FROM_ANTHESIS'] = shaded[DD_SHADING] - shaded[DD_ANTHESIS]
    shaded = shaded.dropna(subset=['DD_FROM_ANTHESIS', 'PCT'])
    shaded['DD_BIN'] = bin_centre(shaded['DD_FROM_ANTHESIS'])

    # one value per site x bin x year
    per_year = shaded.groupby(['SITE', 'DD_BIN', 'YEAR'], as_index=False).agg(
        PCT=('PCT', 'mean'))

    bins = per_year.groupby(['SITE', 'DD_BIN'], as_index=False).agg(
        MEAN=('PCT', 'mean'),
        SD=('PCT', 'std'),                 # ddof = 1
        N_YEARS=('YEAR', 'nunique'))
    bins['BIN_LOWER'] = bins['DD_BIN'] - BIN_WIDTH / 2
    bins['BIN_UPPER'] = bins['DD_BIN'] + BIN_WIDTH / 2
    half = t_half_width(bins['SD'], bins['N_YEARS'])
    bins['CI_LOW'], bins['CI_HIGH'] = bins['MEAN'] - half, bins['MEAN'] + half

    ok = bins[bins['N_YEARS'] >= MIN_YEARS]
    largest = ok.loc[ok.groupby('SITE')['MEAN'].idxmin()]

    largest = largest.set_index('SITE').loc[pf.site_order].reset_index()
    return largest


# ══════════════════════════ FISCHER ══════════════════════════
def load_digitised(file_name):
    df = pd.read_csv(FISCHER_DIR / file_name)
    df['DAYS_AFTER_SOWING'] = df['DAYS_AFTER_SOWING'].round(0).astype('int64')
    dup = df.loc[df['DAYS_AFTER_SOWING'].duplicated(), 'DAYS_AFTER_SOWING'].tolist()
    if dup:
        raise ValueError(f'{file_name}: several points round to the same day {dup}. '
                         'Check the digitised values.')
    return df


def fischer_largest_reduction():
    """Row of the Fischer Expt 74A grain-number point with the lowest % of control."""
    weather = pd.read_csv(FISCHER_DIR / FISCHER_WEATHER_FILE)
    rows = weather.loc[weather['DAS'] == FISCHER_ANTHESIS_DAS, 'ACCUMULATED_TEMP']
    if len(rows) != 1:
        raise ValueError(f'Expected one weather row for DAS {FISCHER_ANTHESIS_DAS}, '
                         f'found {len(rows)}')
    anth_gdd = rows.iloc[0]

    grain = weather.merge(load_digitised(FISCHER_GRAIN_FILE), left_on='DAS',
                          right_on='DAYS_AFTER_SOWING', how='left', validate='one_to_one')
    grain = grain.dropna(subset=[FISCHER_PCT_COL])
    grain['DEGREE_DAYS_FROM_ANTHESIS'] = grain['ACCUMULATED_TEMP'] - anth_gdd

    return grain.loc[grain[FISCHER_PCT_COL].idxmin()]


# ══════════════════════════ TABLE ══════════════════════════
def mean_sd_ci(values, decimals=1):
    """'mean ± SD (95% CI low – high)' across sites."""
    v = pd.Series(values, dtype=float)
    m, sd, n = v.mean(), v.std(), v.count()
    h = t_half_width(sd, n)
    f = f'{{:.{decimals}f}}'
    return (f'{f.format(m)} ± {f.format(sd)} '
            f'({CI_LEVEL:.0%} CI {f.format(m - h)} – {f.format(m + h)})')


def build_table(largest, fischer_min_pct):
    largest = largest.copy()
    largest['DIFF'] = fischer_min_pct - largest['MEAN']

    table = pd.DataFrame({
        COL_SITE: pf.format_site_names(largest['SITE'].astype(str)).values,
        COL_MEAN: (largest['MEAN'].map('{:.1f}'.format) + ' ± '
                   + largest['SD'].map('{:.1f}'.format)).values,
        COL_CI: (largest['CI_LOW'].map('{:.1f}'.format) + ' – '
                 + largest['CI_HIGH'].map('{:.1f}'.format)).values,
        COL_DIFF: largest['DIFF'].map('{:.1f}'.format).values,
        COL_N: largest['N_YEARS'].astype(int).astype(str).values,
        COL_DD: (largest['BIN_LOWER'].map('{:.0f}'.format) + ' – '
                 + largest['BIN_UPPER'].map('{:.0f}'.format)).values,
    })

    # Average across all sites (n = number of sites)
    site_means = largest['MEAN']
    m, sd, n = site_means.mean(), site_means.std(), site_means.count()
    h = t_half_width(sd, n)
    average = {
        COL_SITE: 'Average across all sites',
        COL_MEAN: f'{m:.1f} ± {sd:.1f}',
        COL_CI: f'{m - h:.1f} – {m + h:.1f}',
        COL_DIFF: mean_sd_ci(largest['DIFF'], 1),
        COL_N: mean_sd_ci(largest['N_YEARS'], 1),
        COL_DD: mean_sd_ci(largest['DD_BIN'], 0),
    }
    return pd.concat([table, pd.DataFrame([average])], ignore_index=True)


def main():
    largest = apsim_largest_reduction_by_site()
    fischer = fischer_largest_reduction()
    fischer_min = fischer[FISCHER_PCT_COL]
    print(f"Fischer Expt 74A largest reduction: {fischer_min:.1f}% of unshaded control "
          f"at {fischer['DEGREE_DAYS_FROM_ANTHESIS']:.0f} °Cd from anthesis")

    table = build_table(largest, fischer_min)
    print(f'\n{CULTIVAR}: largest mean reduction in {RESPONSE} by site')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ±, ° and – correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()