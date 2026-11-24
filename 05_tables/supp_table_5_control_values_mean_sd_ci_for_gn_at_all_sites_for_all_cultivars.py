"""
Supplementary Table 5. Control grain numbers ± standard deviations with 95%
confidence intervals for all cultivars at each case study site as shown in
Figure 6.

Control (unshaded) runs only; one value per cultivar x site x year (year =
replicate). Each cell is "mean ± SD" with "(95% CI lower – upper)" on a second
line inside the same cell, t-based CI. Rows = cultivars, columns = sites.

Output: supp_table_5_control_values_mean_sd_ci_for_gn_at_all_sites_for_all_
cultivars.csv in cfg.SECOND_DRAFT_DIR.
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

RESPONSE = 'GRAIN_NUMBER_MATURITY'
CONTROL_LABEL = 'control'
CI_LEVEL = 0.95
DECIMALS = 0

OUTPUT_FILE = 'supp_table_5_control_values_mean_sd_ci_for_gn_at_all_sites_for_all_cultivars.csv'


def load_control():
    """One value per cultivar x site x year, control runs only (all cultivars)."""
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR', RESPONSE]
    df = pd.read_parquet(APSIM_FILE, columns=cols)
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    df = df[df['VARIABLE'] == CONTROL_LABEL]
    if df.empty:
        raise ValueError(f'No rows with VARIABLE == {CONTROL_LABEL!r}')

    return (df.groupby(['CULTIVAR', 'SITE', 'YEAR'], as_index=False)[RESPONSE].mean()
              .dropna(subset=[RESPONSE]))


def summarise(site_year):
    """Mean, SD, n years and t-based CI per cultivar x site."""
    summ = site_year.groupby(['CULTIVAR', 'SITE'], as_index=False).agg(
        MEAN=(RESPONSE, 'mean'),
        SD=(RESPONSE, 'std'),                  # ddof = 1
        N_YEARS=('YEAR', 'nunique'))

    t_crit = stats.t.ppf((1 + CI_LEVEL) / 2, df=summ['N_YEARS'] - 1)
    se = summ['SD'] / np.sqrt(summ['N_YEARS'])
    summ['CI_LOWER'] = summ['MEAN'] - t_crit * se
    summ['CI_UPPER'] = summ['MEAN'] + t_crit * se
    return summ


def fmt_cell(row):
    d = DECIMALS
    if pd.isna(row['SD']):                     # only 1 year -> no SD/CI
        return f"{row['MEAN']:.{d}f}"
    return (f"{row['MEAN']:.{d}f} ± {row['SD']:.{d}f}\n"
            f"({row['CI_LOWER']:.{d}f} – {row['CI_UPPER']:.{d}f})")


def ordered(present, preferred, name):
    order = [x for x in preferred if x in present]
    extra = sorted(x for x in present if x not in order)
    if extra:
        print(f'Warning: {name} not in preferred order (added at end): {extra}')
    return order + extra


def build_table(summ):
    summ = summ.assign(CELL=summ.apply(fmt_cell, axis=1))
    sites = ordered(summ['SITE'].unique(), pf.site_order, 'sites')
    cultivars = ordered(summ['CULTIVAR'].unique(), pf.cultivar_order, 'cultivars')

    table = (summ.pivot(index='CULTIVAR', columns='SITE', values='CELL')
                 .reindex(index=cultivars, columns=sites))
    table.columns = list(pf.format_site_names(pd.Series(sites)))
    return table.reset_index().rename(columns={'CULTIVAR': 'Cultivar'})


def main():
    summ = summarise(load_control())
    n_years = summ.groupby('SITE')['N_YEARS'].agg(['min', 'max'])
    print(f'Years per site (min/max across cultivars):\n{n_years.to_string()}')

    table = build_table(summ)
    pd.set_option('display.width', 250)
    print('\nControl grain number by cultivar and site')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ± and – correctly; the line break inside each
    # cell is kept because pandas quotes cells containing newlines
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()