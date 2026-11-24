#!/usr/bin/env python3
"""
Figure 8: dryland vs irrigated (no water stress) shading experiments, one cultivar
(cfg.EXAMPLE_CULTIVAR), one panel per site.

x  = thermal time (°Cd) from anthesis to the middle of the shading window
y  = % of the same-dataset, same-site, same-year unshaded control
Points: light = every shaded simulation; bars = 95% CI (t, n - 1 df, n = years);
markers = mean across years per DD_BIN_WIDTH °Cd bin, filled if significantly different
from the control (Holm-adjusted). One figure per test (pf.TESTS).
Growth stages are drawn for each dataset (one line style per dataset).

Run from the command line:
    python fig_7_dryland_vs_irrigated_by_site_paired_ttest.py
Shared settings (colours, labels, stage lines, statistics) are in paper_1_functions.py.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import pandas as pd                      # noqa: E402

SCRIPTS_BASE = Path(__file__).resolve().parents[1]
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
FILE_BASE = 'figure_7_dryland_vs_irrigated'

# Summarised and tested: all of these. Drawn: PLOT_VARS.
RAW_VARS = ['GRAIN_NUMBER_MATURITY', 'GRAIN_SIZE_MATURITY', 'YIELD_MATURITY']
PLOT_VARS = [
    'GRAIN_NUMBER_MATURITY',
    # 'GRAIN_SIZE_MATURITY',
    # 'YIELD_MATURITY',
]
PLOT_DATASETS = ['irrigated', 'dryland']      # drawn in this order (later = on top)
COLOUR_BY = 'dataset'           # 'dataset': colour = dataset, marker = variable
                                # 'variable': colour = variable, marker = dataset
STAGE_LABEL_DATASET = 'dryland' # stage abbreviations and ranges drawn for this dataset

N_COLS = 2
FIG_HEIGHT_MM = pf.MAX_FIG_HEIGHT_MM
Y_LIM = None                    # e.g. (70, 130); None = automatic, the same on every panel
X_LIM = None                    # e.g. (-800, 600); None = each site's own data range
X_MAJOR, X_MINOR = pf.DD_MAJOR, pf.DD_MINOR
SHOW_RAW = True
SHOW_CI = True

NUMBERS_VAR = 'GRAIN_NUMBER_MATURITY'


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    raws, shadeds = [], []
    for name, path in DATASET_PATHS.items():
        print(f'{name}: {path}')
        df = pf.load_shading_data(path, RAW_VARS, filters={'CULTIVAR': CULTIVAR})
        df.insert(0, 'DATASET', name)
        raws.append(df)
        shadeds.append(pf.add_dd_from_anthesis(pf.percent_of_control(df, RAW_VARS, keys=('DATASET', 'SITE', 'CULTIVAR'))))
    df = pd.concat(raws, ignore_index=True)
    shaded = pd.concat(shadeds, ignore_index=True)
    sites = [s for s in pf.site_order if s in set(shaded['SITE'])]
    print(f'{CULTIVAR}: {len(sites)} sites {sites}')
    print(shaded.groupby(['SITE', 'DATASET'])['YEAR'].nunique().unstack('DATASET'))
    groups = ['DATASET', 'SITE', 'CULTIVAR']
    per_year, summary = pf.summarise_shading(shaded, RAW_VARS, groups)
    stages = pf.stage_summary(df, groups)
    return shaded, per_year, summary, stages, sites


def series_style(ds, var):
    """(colour, marker, legend label) of one dataset x variable series."""
    d, v = pf.DATASET_STYLES[ds], pf.var_style(var)
    if COLOUR_BY == 'dataset':
        color, marker = d['color'], (v['marker'] if len(PLOT_VARS) > 1 else d['marker'])
    else:
        color, marker = v['color'], d['marker']
    if len(PLOT_VARS) == 1:
        label = d['label']
    elif len(PLOT_DATASETS) == 1:
        label = v['label']
    else:
        label = f"{v['label']}, {d['short']}"
    return color, marker, label


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(test, shaded, summary, stages, sites):
    fig, axes = pf.panel_grid(len(sites), N_COLS, FIG_HEIGHT_MM, sharey=True)
    used = set()
    for k, (ax, site) in enumerate(zip(axes, sites)):
        for var in PLOT_VARS:
            for ds in PLOT_DATASETS:
                color, marker, _ = series_style(ds, var)
                s = summary[(summary['SITE'] == site) & (summary['VAR'] == var) & (summary['DATASET'] == ds)]
                raw = shaded[(shaded['SITE'] == site) & (shaded['DATASET'] == ds)]
                used |= pf.draw_series(ax, s, test, color, marker=marker, raw=raw, raw_y=pf.pct_col(var),
                                       show_raw=SHOW_RAW, show_ci=SHOW_CI)
        pf.draw_control_line(ax)
        ax.set_xlim(*(X_LIM or pf.x_limits(shaded.loc[shaded['SITE'] == site, pf.X_COL])))
        pf.format_dd_axis(ax, X_MAJOR, X_MINOR)
        ax.tick_params(labelbottom=True)
        pf.panel_title(ax, k, pf.format_site_name(site))

    shown = summary[summary['SITE'].isin(sites) & summary['VAR'].isin(PLOT_VARS) & summary['DATASET'].isin(PLOT_DATASETS)]
    pf.shared_ylim(axes, shown, Y_LIM, include_ci=SHOW_CI)
    for ax, site in zip(axes, sites):
        for ds in PLOT_DATASETS:
            label_ds = ds == STAGE_LABEL_DATASET
            pf.draw_stages(ax, pf.stages_for(stages, DATASET=ds, SITE=site, CULTIVAR=CULTIVAR),
                           labels=label_ds, ranges=label_ds,
                           linestyle=pf.DATASET_STYLES[ds]['stage_linestyle'])

    fig.supylabel(pf.YLABEL_PCT, fontsize=pf.FONT_SIZE_NORMAL)
    series = [series_style(ds, v) for v in PLOT_VARS for ds in PLOT_DATASETS]
    stage_ls = [pf.mlines.Line2D([], [], color='#4D4D4D', linewidth=pf.LW_LEGEND,
                                 linestyle=pf.DATASET_STYLES[ds]['stage_linestyle'],
                                 label=f"Stages, {pf.DATASET_STYLES[ds]['short']}") for ds in PLOT_DATASETS]
    pf.figure_legend(fig, [
        ('Simulation', pf.handles_series([(lab, c, m) for c, m, lab in series])),
        (pf.TEST_SHORT[test].capitalize(), pf.handles_stats(test, used)),
        ('Data', pf.handles_data()),
        ('Growth stage', pf.handles_stages() + stage_ls),
    ], xlabel=pf.XLABEL_DD)
    return fig


def main():
    start = pf.start_script(__file__)
    shaded, per_year, summary, stages, sites = prepare()
    tag = '_'.join(pf.var_style(v)['short'].lower() for v in PLOT_VARS)
    for test in pf.TESTS:
        fig = make_figure(test, shaded, summary, stages, sites)
        pf.save(fig, f'{FILE_BASE}_{tag}_{test}')
        win = pf.significant_windows(summary, test, ['DATASET', 'SITE', 'CULTIVAR'])
        pf.save_table(win[win['VAR'] == NUMBERS_VAR].round(0), f'{FILE_BASE}_{test}_significant_windows')
    pf.save_table(summary, f'{FILE_BASE}_bin_summary_tests')
    pf.save_table(per_year, f'{FILE_BASE}_per_year_bins')
    pf.save_table(stages, f'{FILE_BASE}_growth_stages_dd')
    pf.print_stage_caption()
    pf.finish_script(start)


if __name__ == '__main__':
    main()
