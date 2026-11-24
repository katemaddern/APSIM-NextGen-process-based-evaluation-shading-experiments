"""
Supplementary Table 2: mean control (unshaded) values of grain number and its
model terms by site, for cfg.EXAMPLE_CULTIVAR.

Each cell is "mean ± SD (95% CI lower – upper)" across years (year = replicate,
t-based CI).

Output: supp_table_2_mean_grain_number_model_terms_all_sites_{CULTIVAR}.csv
in cfg.SECOND_DRAFT_DIR.
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
CONTROL_LABEL = 'control'
CI_LEVEL = 0.95

# APSIM column -> (column heading, decimals)
RESPONSES = {
    'GRAIN_NUMBER_MATURITY':                 ('Grain Number (grains/ m2)',                            0),
    'SPIKE_WEIGHT_ANTHESIS_STAGE':           ('Spike Dry Weight at Anthesis (grams / m2)',            1),
    'FRUITING_EFFICIENCY_CRITICAL_PERIOD':   ('Fruiting Efficiency (grains / gram SDWa)',             1),
    'DURATION_CRITICAL_PERIOD':              ('Duration (days)',                                      1),
    'PARTITIONING_TO_SPIKE_CRITICAL_PERIOD': ('Partitioning of growth to spike',                      1),
    'CROP_GROWTH_RATE_CRITICAL_PERIOD':      ('Crop Growth Rate (grams / m2 / day)',                  1),
}

OUTPUT_FILE = f'supp_table_2_control_values_mean_sd_ci_for_gn_sdwa_fe_ds_cgr_ps_for_all_sites_{CULTIVAR}.csv'


def load_control():
    """One value per site x year for each response, control runs only."""
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR'] + list(RESPONSES)
    df = pd.read_parquet(APSIM_FILE, columns=cols, filters=[('CULTIVAR', '==', CULTIVAR)])
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    df = df[df['VARIABLE'] == CONTROL_LABEL]
    if df.empty:
        raise ValueError(f'No control rows found for cultivar {CULTIVAR}')

    return df.groupby(['SITE', 'YEAR'], as_index=False)[list(RESPONSES)].mean()


def summarise(site_year):
    """Mean, SD, n years and t-based CI per site x response."""
    long = (site_year
            .melt(id_vars=['SITE', 'YEAR'], value_vars=list(RESPONSES),
                  var_name='RESPONSE', value_name='VALUE')
            .dropna(subset=['VALUE']))

    summ = long.groupby(['SITE', 'RESPONSE'], as_index=False).agg(
        MEAN=('VALUE', 'mean'),
        SD=('VALUE', 'std'),                   # ddof = 1
        N_YEARS=('YEAR', 'nunique'))

    t_crit = stats.t.ppf((1 + CI_LEVEL) / 2, df=summ['N_YEARS'] - 1)
    se = summ['SD'] / np.sqrt(summ['N_YEARS'])
    summ['CI_LOWER'] = summ['MEAN'] - t_crit * se
    summ['CI_UPPER'] = summ['MEAN'] + t_crit * se
    return summ


def fmt_cell(row):
    d = RESPONSES[row['RESPONSE']][1]
    if pd.isna(row['SD']):                     # only 1 year -> no SD/CI
        return f"{row['MEAN']:.{d}f}"
    return (f"{row['MEAN']:.{d}f} ± {row['SD']:.{d}f} "
            f"({row['CI_LOWER']:.{d}f} – {row['CI_UPPER']:.{d}f})")


def site_order(present):
    order = [s for s in pf.site_order if s in present]
    extra = sorted(s for s in present if s not in order)
    if extra:
        print(f'Warning: sites not in pf.site_order (added at end): {extra}')
    return order + extra


def build_table(summ):
    summ = summ.copy()
    summ['CELL'] = summ.apply(fmt_cell, axis=1)
    sites = site_order(summ['SITE'].unique())

    table = (summ.pivot(index='SITE', columns='RESPONSE', values='CELL')
                 .reindex(index=sites, columns=list(RESPONSES))
                 .rename(columns={k: name for k, (name, _) in RESPONSES.items()})
                 .reset_index())
    table.columns.name = None
    table['SITE'] = pf.format_site_names(table['SITE'].astype(str))
    return table.rename(columns={'SITE': 'Site'})


def main():
    site_year = load_control()
    n_years = site_year.groupby('SITE')['YEAR'].nunique()
    print(f'Years per site: {n_years.to_dict()}')

    table = build_table(summarise(site_year))
    pd.set_option('display.width', 250)
    print(f'\n{CULTIVAR}: mean control values by site')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ± and – correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()