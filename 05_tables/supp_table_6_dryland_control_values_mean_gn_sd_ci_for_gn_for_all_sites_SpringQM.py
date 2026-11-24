"""
Supplementary Table 6. Control grain numbers ± standard deviations with 95%
confidence intervals for standard growing condition simulations in Figure 7
for the Spring Quick Mid cultivar (cfg.EXAMPLE_CULTIVAR).

Standard growing conditions = the 'dryland' dataset. Control (unshaded) runs
only; one value per site x year (year = replicate). Each cell is
"mean ± SD (95% CI lower – upper)", t-based CI.

Output: supp_table_6_control_values_mean_sd_ci_for_gn_all_sites_standard_
growing_conditions_{CULTIVAR}.csv in cfg.SECOND_DRAFT_DIR.
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
# Key = dataset name used in pf.DATASET_STYLES, the DATASET column and file names
# Each dataset: (full file, limited file for upload). The full file is used if it exists.
DATASET_FILES = {
    'dryland':   (Path(cfg.DRYLAND_SHADED_DF), Path(cfg.LIMITED_DRYLAND_SHADED_DF)),
    'irrigated': (Path(cfg.ALL_DATA_SHADED_DF), Path(cfg.LIMITED_SHADED_DF)),   # fully irrigated, no water stress
}

DATASET_PATHS = {}
for name, (full, limited) in DATASET_FILES.items():
    if full.is_file():
        DATASET_PATHS[name] = full
        print(f'{name} data: full file {full}')
    elif limited.is_file():
        DATASET_PATHS[name] = limited
        print(f'{name} data: full file not found, using the limited file {limited}')
    else:
        raise FileNotFoundError(f'No {name} data file found:\n  {full}\n  {limited}')

CULTIVAR = cfg.EXAMPLE_CULTIVAR
DATASET = 'dryland'             # standard growing conditions
CONTROL_LABEL = 'control'
CI_LEVEL = 0.95

# APSIM column -> (column heading, decimals)
RESPONSES = {
    'GRAIN_NUMBER_MATURITY': ('Grain Number (grains/ m2)', 0),
}

OUTPUT_FILE = (f'supp_table_6_control_values_mean_sd_ci_for_gn_all_sites_'
               f'standard_growing_conditions_{CULTIVAR}.csv')


def load_control(path):
    """One value per site x year for each response, control runs only."""
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR'] + list(RESPONSES)
    df = pd.read_parquet(path, columns=cols, filters=[('CULTIVAR', '==', CULTIVAR)])
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    df = df[df['VARIABLE'] == CONTROL_LABEL]
    if df.empty:
        raise ValueError(f'No control rows found for cultivar {CULTIVAR} in {path}')

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
    site_year = load_control(DATASET_PATHS[DATASET])
    n_years = site_year.groupby('SITE')['YEAR'].nunique()
    print(f'Years per site: {n_years.to_dict()}')

    table = build_table(summarise(site_year))
    pd.set_option('display.width', 250)
    print(f'\n{CULTIVAR}: control grain number by site, standard growing conditions ({DATASET})')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ± and – correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()