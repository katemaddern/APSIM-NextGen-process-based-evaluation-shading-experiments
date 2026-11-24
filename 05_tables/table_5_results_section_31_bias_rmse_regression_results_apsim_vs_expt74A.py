"""
Results 3.1, Table 5: agreement between APSIM NextGen and Fischer (1985) Expt 74A.

Each of the 15 shading timings of Expt 74A is compared with the 30-year mean
APSIM response in the 20 °Cd bin containing it (thermal time from anthesis to
the middle of the shading window). Both series are reductions in grain number,
in percentage points (pp) of the unshaded control:
    reduction = 100 - grain number as % of control

  Bias       = mean(simulated - observed); positive = APSIM simulates a larger reduction
  RMSE       = root mean square error
  Slope, intercept, R² = regression of observed on simulated (Piñeiro et al. 2008)

The final row, 'All sites', gives the mean ± SD of the eight site values with a
t-based 95% CI (n = 8 sites).

Output: table_5_results_section_31_bias_RMSE_and_regression_of_simulated_vs_
observed_expt74A.csv in cfg.SECOND_DRAFT_DIR.
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
SHADED_LABEL = 'radiation'      # VARIABLE value of shaded runs
CONTROL_LABEL = 'control'       # VARIABLE value of unshaded control runs
RESPONSE = 'GRAIN_NUMBER_MATURITY'
BIN_WIDTH = 20.0                # thermal-time bin width (°Cd)
MIN_YEARS = 5                   # bins with fewer years are blanked
CI_LEVEL = 0.95

FISCHER_WEATHER_FILE = 'fischer_1985_daily_temp_radiation.csv'   # daily weather
FISCHER_GRAIN_FILE = 'fischer_grain_number_data.csv'             # digitised Fig. 1 points
FISCHER_ANTHESIS_DAS = 86       # days after sowing to 50% anthesis (Fischer 1975, p. 610)
FISCHER_PCT_COL = 'GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'

OUTPUT_FILE = ('table_5_results_section_31_bias_RMSE_and_regression_of_'
               'simulated_vs_observed_expt74A.csv')
ALL_SITES_LABEL = 'All sites'

# metric -> (column heading, decimals)
TABLE_COLUMNS = {
    'BIAS':      ('Bias (pp)',                 1),
    'RMSE':      ('RMSE (pp)',                 1),
    'SLOPE':     ('Regression slope',          2),
    'INTERCEPT': ('Regression intercept (pp)', 2),
    'R2':        ('R²',                        2),
}


def to_bin(x):
    """Bin centre; rounding before flooring stops values on a bin edge being split by float error."""
    return (np.floor(np.round(x / BIN_WIDTH, 9)) * BIN_WIDTH + BIN_WIDTH / 2).round(6)


def t_crit(dof):
    return stats.t.ppf((1 + CI_LEVEL) / 2, dof)


# ══════════════════════════ FISCHER (observed) ══════════════════════════
def load_digitised(file_name):
    df = pd.read_csv(FISCHER_DIR / file_name)
    df['DAYS_AFTER_SOWING'] = df['DAYS_AFTER_SOWING'].round(0).astype('int64')
    dup = df.loc[df['DAYS_AFTER_SOWING'].duplicated(), 'DAYS_AFTER_SOWING'].tolist()
    if dup:
        raise ValueError(f'{file_name}: several points round to the same day {dup}. '
                         'Check the digitised values.')
    return df


def load_fischer():
    weather = pd.read_csv(FISCHER_DIR / FISCHER_WEATHER_FILE)
    rows = weather.loc[weather['DAS'] == FISCHER_ANTHESIS_DAS, 'ACCUMULATED_TEMP']
    if len(rows) != 1:
        raise ValueError(f'Expected one weather row for DAS {FISCHER_ANTHESIS_DAS}, '
                         f'found {len(rows)}')
    anthesis_gdd = rows.iloc[0]

    f = weather.merge(load_digitised(FISCHER_GRAIN_FILE), left_on='DAS',
                      right_on='DAYS_AFTER_SOWING', how='left', validate='one_to_one')
    f = f.dropna(subset=[FISCHER_PCT_COL])
    f['FISCHER_GDD'] = f['ACCUMULATED_TEMP'] - anthesis_gdd
    f['OBS_REDUCTION'] = 100 - f[FISCHER_PCT_COL]
    f['FISCHER_BIN'] = to_bin(f['FISCHER_GDD'])

    f = f[['FISCHER_GDD', 'FISCHER_BIN', 'OBS_REDUCTION']].sort_values('FISCHER_GDD')
    print(f'Fischer: {len(f)} grain-number points. Anthesis = {anthesis_gdd:.0f} °Cd after sowing.')
    return f.reset_index(drop=True)


# ══════════════════════════ APSIM (simulated) ══════════════════════════
def load_apsim_curves():
    """Per site: Series of the 30-year mean simulated reduction (pp), indexed by bin centre."""
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR', 'SHIFT_DOY', 'DOY_MATURITY', RESPONSE,
            'CUM_DEGREE_DAY_ANTHESIS_STAGE', 'CUM_DEGREE_DAY_MID_SHADING']
    df = pd.read_parquet(APSIM_FILE, columns=cols, filters=[('CULTIVAR', '==', CULTIVAR)])
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.lower().str.strip()
    for c in ['SHIFT_DOY', 'DOY_MATURITY', RESPONSE,
              'CUM_DEGREE_DAY_ANTHESIS_STAGE', 'CUM_DEGREE_DAY_MID_SHADING']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    is_control = df['VARIABLE'] == CONTROL_LABEL
    is_shaded = df['VARIABLE'] == SHADED_LABEL
    # drop shading windows whose middle is after maturity (control rows kept)
    df = df[is_control | (is_shaded & (df['SHIFT_DOY'] <= df['DOY_MATURITY']))]

    # same-year control
    control = df.loc[df['VARIABLE'] == CONTROL_LABEL, ['SITE', 'YEAR', RESPONSE]]
    n_dup = control.duplicated(['SITE', 'YEAR']).sum()
    if n_dup:
        raise ValueError(f'{n_dup} site-years have more than one control run. Check the filters.')
    control = control.rename(columns={RESPONSE: 'CONTROL'})

    shaded = df[df['VARIABLE'] == SHADED_LABEL].merge(
        control, on=['SITE', 'YEAR'], how='left', validate='many_to_one')
    shaded['DD_FROM_ANTHESIS'] = (shaded['CUM_DEGREE_DAY_MID_SHADING']
                                  - shaded['CUM_DEGREE_DAY_ANTHESIS_STAGE'])
    shaded = shaded.dropna(subset=['DD_FROM_ANTHESIS', RESPONSE])
    missing_ctrl = shaded['CONTROL'].isna()
    if missing_ctrl.any():
        print(f'WARNING: {missing_ctrl.sum()} shaded rows have no same-year control and are dropped.')
        shaded = shaded[~missing_ctrl]
    shaded['BIN'] = to_bin(shaded['DD_FROM_ANTHESIS'])

    # one value per site x year x bin
    paired = shaded.groupby(['SITE', 'YEAR', 'BIN'], as_index=False).agg(
        shaded=(RESPONSE, 'mean'), control=('CONTROL', 'first'))
    paired['SIM_REDUCTION'] = -100 * (paired['shaded'] - paired['control']) / paired['control']
    paired = paired.dropna(subset=['SIM_REDUCTION'])

    curves = {}
    for site, g in paired.groupby('SITE'):
        wide = g.pivot_table(index='YEAR', columns='BIN', values='SIM_REDUCTION', aggfunc='mean')
        wide.loc[:, wide.notna().sum() < MIN_YEARS] = np.nan   # too few years
        curves[site] = wide.mean()                              # mean over years, per bin
    return curves


# ══════════════════════════ METRICS ══════════════════════════
def agreement_metrics(obs, sim):
    ok = np.isfinite(obs) & np.isfinite(sim)
    obs, sim = obs[ok], sim[ok]
    err = sim - obs
    reg = stats.linregress(sim, obs)          # observed = a + b * simulated
    return {
        'BIAS': err.mean(),
        'RMSE': np.sqrt(np.mean(err ** 2)),
        'SLOPE': reg.slope,
        'INTERCEPT': reg.intercept,
        'R2': reg.rvalue ** 2,
        'N_POINTS': int(ok.sum()),
    }


def fmt(x, d):
    return f'{round(x, d) + 0.0:.{d}f}'       # + 0.0 so -0.0 prints as 0.0


def build_table(fischer, curves):
    sites = [s for s in pf.site_order if s in curves]
    missing = [s for s in pf.site_order if s not in curves]
    if missing:
        print(f'WARNING: sites in pf.site_order with no APSIM data: {missing}')

    obs = fischer['OBS_REDUCTION'].to_numpy(float)
    metrics = {}
    for site in sites:
        sim = curves[site].reindex(fischer['FISCHER_BIN']).to_numpy(float)
        m = agreement_metrics(obs, sim)
        if m['N_POINTS'] < len(obs):
            print(f'{site}: {len(obs) - m["N_POINTS"]} Fischer points outside simulated bins (dropped)')
        metrics[site] = m
    metrics = pd.DataFrame(metrics).T

    table = pd.DataFrame({'Site': pf.format_site_names(pd.Series(sites)).values})
    for key, (name, d) in TABLE_COLUMNS.items():
        table[name] = [fmt(v, d) for v in metrics[key].astype(float)]

    # All sites: mean ± SD (95% CI) across the site values
    all_row = {'Site': ALL_SITES_LABEL}
    for key, (name, d) in TABLE_COLUMNS.items():
        v = metrics[key].astype(float)
        m, sd, n = v.mean(), v.std(ddof=1), v.count()
        h = t_crit(n - 1) * sd / np.sqrt(n)
        all_row[name] = (f'{fmt(m, d)} ± {fmt(sd, d)} '
                         f'({CI_LEVEL:.0%} CI {fmt(m - h, d)} – {fmt(m + h, d)})')
    return pd.concat([table, pd.DataFrame([all_row])], ignore_index=True)


def main():
    fischer = load_fischer()
    curves = load_apsim_curves()
    table = build_table(fischer, curves)

    pd.set_option('display.width', 250)
    print(f'\n{CULTIVAR}: agreement between APSIM and Fischer (1985) Expt 74A')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ±, ² and – correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()