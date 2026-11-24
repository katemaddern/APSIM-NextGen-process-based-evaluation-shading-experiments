"""
Supplementary Table 7. Maximum grain number reduction comparison between
non-irrigated (standard) and irrigated simulated shading experiments for the
Spring Quick Mid cultivar (cfg.EXAMPLE_CULTIVAR), as shown in Figure 7.

For each dataset and site, APSIM grain number at maturity in each shaded run is
expressed as % of the same-year control. Shading windows are binned by thermal
time from anthesis (window mid-point, 20 °Cd bins), averaged within year, then
across years. The bin with the lowest mean (among bins with >= MIN_YEARS years)
is the site's maximum reduction.

The table reports the dryland result for each site, plus:
  - difference in mean maximum reduction (dryland - irrigated, % of control)
  - difference in timing of the maximum reduction (dryland - irrigated bin
    centre, °Cd); negative = dryland maximum occurs earlier
  - whether the 95% CIs of the dryland and irrigated means overlap

Output: sup_table_7_differences_in_maximum_shaded_gn_reduction_dryland_vs_
irrigated.csv in cfg.SECOND_DRAFT_DIR.
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
RESPONSE = 'GRAIN_NUMBER_MATURITY'
POINT = 'MID'            # shading window point: 'START', 'MID' or 'END'
BIN_WIDTH = 20.0         # °Cd
MIN_YEARS = 5            # bins with fewer years are not eligible
CI_LEVEL = 0.95

DD_SHADING = f'CUM_DEGREE_DAY_{POINT}_SHADING'
DD_ANTHESIS = 'CUM_DEGREE_DAY_ANTHESIS_STAGE'

OUTPUT_FILE = f'sup_table_7_differences_in_maximum_shaded_gn_reduction_dryland_vs_irrigated_{CULTIVAR}.csv'

COL_SITE = 'Site'
COL_MEAN = 'Mean maximum reduction in GN (% ± SD)'
COL_CI = 'Confidence Interval of mean'
COL_N = 'Number of Years in Bin'
COL_DD = 'Degree Days from Anthesis (°Cd)'
COL_DIFF = 'Difference in mean maximum reduction in GN (%) (dryland - irrigated)'
COL_TIMING = 'Difference in timing of mean maximum reduction (°Cd) (dryland - irrigated)'
COL_OVERLAP = 'Overlapping CIs between dryland and irrigated'


def bin_centre(dd):
    return np.floor(np.round(dd / BIN_WIDTH, 9)) * BIN_WIDTH + BIN_WIDTH / 2


def largest_reduction_by_site(name, path):
    """Bin with the lowest mean grain number (% of control) per site, for one dataset."""
    cols = ['SITE', 'YEAR', 'VARIABLE', 'CULTIVAR', 'SHIFT_DOY', 'END_SHADING_DOY',
            'DOY_MATURITY', DD_SHADING, DD_ANTHESIS, RESPONSE]
    df = pd.read_parquet(path, columns=cols, filters=[('CULTIVAR', '==', CULTIVAR)])
    df['VARIABLE'] = df['VARIABLE'].astype(str).str.strip().str.lower()

    # drop shading windows that end after maturity (control runs always kept)
    df = df[(df['VARIABLE'] == 'control') | (df['END_SHADING_DOY'] <= df['DOY_MATURITY'])]

    # % of the same-year control
    ctrl = df[(df['VARIABLE'] == 'control') & (df['SHIFT_DOY'] == 0)]
    assert not ctrl.duplicated(['SITE', 'YEAR']).any(), f'{name}: duplicate control runs'
    ctrl = ctrl[['SITE', 'YEAR', RESPONSE]].rename(columns={RESPONSE: 'CONTROL'})

    shaded = df[df['VARIABLE'] == 'radiation'].merge(
        ctrl, on=['SITE', 'YEAR'], how='inner', validate='many_to_one')
    shaded['PCT'] = 100 * shaded[RESPONSE] / shaded['CONTROL']

    # thermal time from anthesis and bin
    shaded['DD_FROM_ANTHESIS'] = shaded[DD_SHADING] - shaded[DD_ANTHESIS]
    shaded = shaded.dropna(subset=['DD_FROM_ANTHESIS', 'PCT'])
    shaded['DD_BIN'] = bin_centre(shaded['DD_FROM_ANTHESIS'])

    # one value per site x bin x year
    per_year = shaded.groupby(['SITE', 'DD_BIN', 'YEAR'], as_index=False).agg(PCT=('PCT', 'mean'))

    bins = per_year.groupby(['SITE', 'DD_BIN'], as_index=False).agg(
        MEAN=('PCT', 'mean'),
        SD=('PCT', 'std'),                 # ddof = 1
        N_YEARS=('YEAR', 'nunique'))
    bins['BIN_LOWER'] = bins['DD_BIN'] - BIN_WIDTH / 2
    bins['BIN_UPPER'] = bins['DD_BIN'] + BIN_WIDTH / 2
    half = (stats.t.ppf(0.5 + CI_LEVEL / 2, bins['N_YEARS'] - 1)
            * bins['SD'] / np.sqrt(bins['N_YEARS']))
    bins['CI_LOW'], bins['CI_HIGH'] = bins['MEAN'] - half, bins['MEAN'] + half

    ok = bins[bins['N_YEARS'] >= MIN_YEARS]
    largest = ok.loc[ok.groupby('SITE')['MEAN'].idxmin()]
    return largest.set_index('SITE')


def build_table(dry, irr):
    sites = [s for s in pf.site_order if s in dry.index and s in irr.index]
    missing = [s for s in pf.site_order if s not in sites]
    if missing:
        print(f'WARNING: sites missing from one or both datasets: {missing}')
    dry, irr = dry.loc[sites], irr.loc[sites]

    overlap = (dry['CI_LOW'] <= irr['CI_HIGH']) & (irr['CI_LOW'] <= dry['CI_HIGH'])

    table = pd.DataFrame({
        COL_SITE: pf.format_site_names(pd.Series(sites)).values,
        COL_MEAN: (dry['MEAN'].map('{:.1f}'.format) + ' ± ' + dry['SD'].map('{:.1f}'.format)).values,
        COL_CI: (dry['CI_LOW'].map('{:.1f}'.format) + ' – ' + dry['CI_HIGH'].map('{:.1f}'.format)).values,
        COL_N: dry['N_YEARS'].astype(int).values,
        COL_DD: (dry['BIN_LOWER'].map('{:.0f}'.format) + ' – '
                 + dry['BIN_UPPER'].map('{:.0f}'.format)).values,
        COL_DIFF: [f'{round(v, 1) + 0.0:.1f}' for v in dry['MEAN'] - irr['MEAN']],
        COL_TIMING: [f'{round(v) + 0:.0f}' for v in dry['DD_BIN'] - irr['DD_BIN']],
        COL_OVERLAP: overlap.map({True: 'Yes', False: 'No'}).values,
    })
    return table


def main():
    largest = {name: largest_reduction_by_site(name, path) for name, path in DATASET_PATHS.items()}

    for ds, df in largest.items():
        print(f'\n{ds}: largest mean reduction ({CULTIVAR})')
        print(df[['MEAN', 'SD', 'CI_LOW', 'CI_HIGH', 'N_YEARS', 'DD_BIN']].round(1).to_string())

    table = build_table(largest['dryland'], largest['irrigated'])
    pd.set_option('display.width', 250)
    print(f'\n{CULTIVAR}: maximum reduction in {RESPONSE}, dryland vs irrigated')
    print(table.to_string(index=False))

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ±, ° and – correctly
    table.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nSaved: {out_path}')


if __name__ == '__main__':
    main()