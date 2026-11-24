#!/usr/bin/env python3
"""
Figure 5 by site: how shading at different times changes grain number, grain size
and yield, for one cultivar (cfg.EXAMPLE_CULTIVAR). One panel per site.

x  = thermal time (°Cd) from anthesis to the middle of the shading window
y  = % of the same-site, same-year unshaded control
Points: light = every shaded simulation; bars = 95% CI (t, n - 1 df, n = years);
markers = mean across years in each DD_BIN_WIDTH °Cd bin, filled if significantly
different from the control (Holm-adjusted). One figure per test (pf.TESTS).

Run from the command line:
    python fig_5_gn_gs_yield_by_site_paired_ttest.py
Shared settings (colours, labels, stage lines, statistics) are in paper_1_functions.py.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')

SCRIPTS_BASE = Path(__file__).resolve().parents[1]
if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg            # noqa: E402
import paper_1_functions as pf           # noqa: E402

# ══════════════════════════ SETTINGS ══════════════════════════
# APSIM results: the full file if it exists, otherwise the limited file for upload
DATA_PATH_FULL = Path(cfg.ALL_DATA_SHADED_DF)
DATA_PATH_LIMITED = Path(cfg.LIMITED_SHADED_DF)
if DATA_PATH_FULL.is_file():
    DATA_PATH = DATA_PATH_FULL
    print(f'APSIM data: full file {DATA_PATH}')
elif DATA_PATH_LIMITED.is_file():
    DATA_PATH = DATA_PATH_LIMITED
    print(f'APSIM data: full file not found, using the limited file {DATA_PATH}')
else:
    raise FileNotFoundError(f'No APSIM data file found:\n  {DATA_PATH_FULL}\n  {DATA_PATH_LIMITED}')


CULTIVAR = cfg.EXAMPLE_CULTIVAR
FILE_BASE = f'figure_4_all_sites_{CULTIVAR}'

# Every variable is summarised and tested; drawn back to front in this order
# Drawn in this order: first = bottom, last = on top
PLOT_VARS = [
    'GRAIN_NUMBER_MATURITY',
    'GRAIN_SIZE_MATURITY',
    'YIELD_MATURITY',
]

N_COLS = 2
FIG_HEIGHT_MM = pf.MAX_FIG_HEIGHT_MM
Y_LIM = None          # e.g. (40, 130); None = automatic, the same on every panel
X_LIM = None          # e.g. (-800, 600); None = each site's own data range
X_MAJOR, X_MINOR = pf.DD_MAJOR, pf.DD_MINOR
SHOW_RAW = True
SHOW_CI = True

# Variable used for the 'numbers for the text' tables
NUMBERS_VARS = ['GRAIN_NUMBER_MATURITY', 'GRAIN_SIZE_MATURITY', 'YIELD_MATURITY']


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    df = pf.load_shading_data(DATA_PATH, PLOT_VARS, filters={'CULTIVAR': CULTIVAR})
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, PLOT_VARS))
    sites = pf.present_in_order(shaded['SITE'], pf.site_order)
    sites = [s for s in sites if s in pf.site_order]           # only sites in pf.site_order
    print(f'{CULTIVAR}: {len(sites)} sites {sites}')
    per_year, summary = pf.summarise_shading(shaded, PLOT_VARS, ['SITE', 'CULTIVAR'])
    stages = pf.stage_summary(df, ['SITE', 'CULTIVAR'])
    return shaded, per_year, summary, stages, sites


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(test, shaded, summary, stages, sites):
    fig, axes = pf.panel_grid(len(sites), N_COLS, FIG_HEIGHT_MM, sharey=True)
    used = set()
    for k, (ax, site) in enumerate(zip(axes, sites)):
        for var in PLOT_VARS:
            s = summary[(summary['SITE'] == site) & (summary['VAR'] == var)]
            raw = shaded[shaded['SITE'] == site]
            used |= pf.draw_series(ax, s, test, pf.var_color(var), raw=raw, raw_y=pf.pct_col(var),
                                   show_raw=SHOW_RAW, show_ci=SHOW_CI)
        pf.draw_control_line(ax)
        ax.set_xlim(*(X_LIM or pf.x_limits(shaded.loc[shaded['SITE'] == site, pf.X_COL])))
        pf.format_dd_axis(ax, X_MAJOR, X_MINOR)
        ax.tick_params(labelbottom=True)
        pf.panel_title(ax, k, pf.format_site_name(site))

    pf.shared_ylim(axes, summary[summary['SITE'].isin(sites)], Y_LIM, include_ci=SHOW_CI)
    for ax, site in zip(axes, sites):                       # stages last: limits are final
        pf.draw_stages(ax, pf.stages_for(stages, SITE=site, CULTIVAR=CULTIVAR))

    fig.supylabel(pf.YLABEL_PCT, fontsize=pf.FONT_SIZE_NORMAL)
    pf.figure_legend(fig, [
        ('Variable', pf.handles_variables(PLOT_VARS[::-1])),
        (pf.TEST_SHORT[test].capitalize(), pf.handles_stats(test, used)),
        ('Data', pf.handles_data()),
        ('Growth stage', pf.handles_stages()),
    ], xlabel=pf.XLABEL_DD)
    return fig


# ══════════════════════════ NUMBERS FOR THE TEXT ══════════════════════════
def text_numbers(summary, stages, test):
    win = pf.significant_windows(summary, test, ['SITE', 'CULTIVAR'])
    win = win[win['VAR'].isin(NUMBERS_VARS)]
    fla = stages[stages['STAGE'] == 'FLAG_LEAF'][['SITE', 'CULTIVAR', 'MEAN']].rename(columns={'MEAN': 'mean_fla_dd'})
    first_decrease = (summary[summary['MEAN'] < 100].groupby(['SITE', 'CULTIVAR', 'VAR'])['X_MEAN']
                      .min().rename('first_decrease_dd').reset_index())
    out = (win.merge(first_decrease, on=['SITE', 'CULTIVAR', 'VAR'], how='outer')
              .merge(fla, on=['SITE', 'CULTIVAR'], how='left'))
    out = out[out['VAR'].isin(NUMBERS_VARS)]
    out['first_significant_minus_fla'] = out['first_significant'] - out['mean_fla_dd']
    out['first_decrease_minus_fla'] = out['first_decrease_dd'] - out['mean_fla_dd']
    return out.round(0)


def main():
    start = pf.start_script(__file__)
    shaded, per_year, summary, stages, sites = prepare()
    for test in pf.TESTS:
        fig = make_figure(test, shaded, summary, stages, sites)
        pf.save(fig, f'{FILE_BASE}_{test}')
        pf.save_table(text_numbers(summary, stages, test), f'{FILE_BASE}_{test}_significant_windows')
    pf.save_table(summary, f'{FILE_BASE}_bin_summary_tests')
    pf.save_table(per_year, f'{FILE_BASE}_per_year_bins')
    pf.save_table(stages, f'{FILE_BASE}_growth_stages_dd')
    pf.print_stage_caption()
    pf.finish_script(start)


if __name__ == '__main__':
    main()
