"""
Supplementary Table 4. Mean and standard deviation of the duration of the
critical period (days) when calculated using the different definitions for
each cultivar (averaged across all sites).

Control (unshaded) runs only. Duration = end DOY - start DOY of each
definition. One value per cultivar x site x year; every site x year value for
a cultivar is one observation (n = sites x years). Each cell is
"mean ± SD (95% CI lower-upper)", t-based CI.

Output: supp_table_4_control_values_mean_sd_ci_for_each_cp_defintions_and_
each_cultivars_averaged_across_all_sites.csv in cfg.SECOND_DRAFT_DIR.
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

CONTROL_LABEL = 'control'
CI_LEVEL = 0.95
DECIMALS = 1

# Critical-period definitions, in column order. Keys match the APSIM columns
# DOY_CONT_START_<KEY>_CRIT_PERIOD and DOY_CONT_END_<KEY>_CRIT_PERIOD.
CP_DEFINITIONS = {
    'FISCHER_2024': 'Fischer et al. (2024)',
    'ABBATE_1997':  'Abbate et al. (1997)',
    'SLAFER_2021':  'Slafer et al. (2021)',
    'PORKER_2025':  'Porker et al. (2025)',
    'DRECCER_2000': 'Dreccer et al. (2000)',
    'FISCHER_1985': 'Fischer (1985)',
    'SADRAS_2022':  'Sadras et al. (2022)',
    'SLAFER_2023':  'Slafer et al. (2023)',
}

OUTPUT_FILE = ('supp_table_4_control_values_mean_sd_ci_for_each_cp_defintions_'
               'and_each_cultivars_averaged_across_all_sites.csv')


def start_col(k):
    return f'DOY_CONT_START_{k}_CRIT_PERIOD'


def end_col(k):
    return f'DOY_CONT_END_{k}_CRIT_PERIOD'


def load_durations():
    """Long table: CULTIVAR, SITE, YEAR, DEFINITION, LENGTH_DAYS (control runs only)."""
    keys = list(CP_DEFINITIONS)
    doy_cols = [c for k in keys for c in (start_col(k), end_col(k))]
    df = pd.read_parquet(APSIM_FILE, columns=['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR'] + doy_cols)
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    df = df[df['VARIABLE'] == CONTROL_LABEL].copy()
    if df.empty:
        raise ValueError(f'No rows with VARIABLE == {CONTROL_LABEL!r}')

    for k in keys:
        df[k] = df[end_col(k)] - df[start_col(k)]

    neg = {k: int((df[k] < 0).sum()) for k in keys if (df[k] < 0).any()}
    if neg:
        print(f'Warning: negative lengths (end before start) found: {neg}')

    # one value per cultivar x site x year (year = replicate)
    site_year = df.groupby(['CULTIVAR', 'SITE', 'YEAR'], as_index=False)[keys].mean()
    return (site_year
            .melt(id_vars=['CULTIVAR', 'SITE', 'YEAR'], value_vars=keys,
                  var_name='DEFINITION', value_name='LENGTH_DAYS')
            .dropna(subset=['LENGTH_DAYS']))


def summarise_by_cultivar(long):
    """Mean, SD, n and t-based CI per cultivar x definition (all sites x years pooled)."""
    s = long.groupby(['CULTIVAR', 'DEFINITION'], as_index=False).agg(
        N=('LENGTH_DAYS', 'size'),
        N_SITES=('SITE', 'nunique'),
        MEAN=('LENGTH_DAYS', 'mean'),
        SD=('LENGTH_DAYS', 'std'))             # ddof = 1

    t_crit = stats.t.ppf((1 + CI_LEVEL) / 2, df=s['N'] - 1)   # NaN when n = 1
    se = s['SD'] / np.sqrt(s['N'])
    s['CI_LOWER'] = s['MEAN'] - t_crit * se
    s['CI_UPPER'] = s['MEAN'] + t_crit * se
    return s


def fmt_cell(row):
    d = DECIMALS
    if pd.isna(row['SD']):                     # only 1 observation -> no SD/CI
        return f"{row['MEAN']:.{d}f}"
    return (f"{row['MEAN']:.{d}f} ± {row['SD']:.{d}f} "
            f"({row['CI_LOWER']:.{d}f}-{row['CI_UPPER']:.{d}f})")


def cultivar_order(present):
    order = [c for c in pf.cultivar_order if c in present]
    extra = sorted(c for c in present if c not in order)
    if extra:
        print(f'Warning: cultivars not in pf.cultivar_order (added at end): {extra}')
    return order + extra


def build_table(s):
    s = s.assign(CELL=s.apply(fmt_cell, axis=1))
    table = (s.pivot(index='CULTIVAR', columns='DEFINITION', values='CELL')
              .reindex(index=cultivar_order(s['CULTIVAR'].unique()),
                       columns=list(CP_DEFINITIONS))
              .rename(columns=CP_DEFINITIONS)
              .reset_index()
              .rename(columns={'CULTIVAR': 'Cultivar'}))
    table.columns.name = None
    return table


def main():
    long = load_durations()
    s = summarise_by_cultivar(long)
    print('Observations per cultivar (sites x years): '
          f"{s.groupby('CULTIVAR')['N'].max().to_dict()}")

    table = build_table(s)
    pd.set_option('display.width', 250)
    print('\nCritical-period duration (days) by cultivar, averaged across all sites')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ± correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()