#!/usr/bin/env python3
"""
Figure 2 by variable: one cultivar (cfg.EXAMPLE_CULTIVAR), one panel per variable,
one marker colour per site (pf.site_color_dict).

x  = thermal time (°Cd) from anthesis to the middle of the shading window
y  = % of the same-site, same-year unshaded control
Points: light = every shaded simulation; bars = 95% CI (t, n - 1 df, n = years);
markers = mean across years per DD_BIN_WIDTH °Cd bin, filled if significantly different
from the control (Holm-adjusted). One figure per test (pf.TESTS).
Growth stages: each site's mean stage is a tick in the site colour at the top of the
panel; anthesis (0 °Cd at every site) is a full line.

Run from the command line:
    python fig_2_by_variable_degree_days.py
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
FILE_BASE = f'figure_2_all_sites_{CULTIVAR}'

# Panel order: grain number and its components, then the components of spike dry weight
PANEL_VARS = [
    'GRAIN_NUMBER_MATURITY',
    'FRUITING_EFFICIENCY_CRITICAL_PERIOD',
    'SPIKE_WEIGHT_ANTHESIS_STAGE',
    'CROP_GROWTH_RATE_CRITICAL_PERIOD',
    'DURATION_CRITICAL_PERIOD',
    'PARTITIONING_TO_SPIKE_CRITICAL_PERIOD',
]

N_COLS = 2
FIG_HEIGHT_MM = pf.MAX_FIG_HEIGHT_MM
SHARE_Y = False       # variables have very different ranges
Y_LIM = None          # e.g. (40, 130) on every panel; None = automatic per panel
X_LIM = None          # e.g. (-800, 600); None = full data range (same on every panel)
X_MAJOR, X_MINOR = pf.DD_MAJOR, pf.DD_MINOR
SHOW_RAW = False          # True = light background points for every simulation
SHOW_CI = True
SHOW_SITE_TICKS = False   # True = a tick in each site's colour at the top for that site's mean stage
SHOW_STAGE_RANGES = True  # True = green/red spans: range of FLA and MGL across sites and years


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    df = pf.load_shading_data(DATA_PATH, PANEL_VARS, filters={'CULTIVAR': CULTIVAR})
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, PANEL_VARS))
    sites = [s for s in pf.site_order if s in set(shaded['SITE'])]
    print(f'{CULTIVAR}: {len(sites)} sites {sites}')
    per_year, summary = pf.summarise_shading(shaded, PANEL_VARS, ['SITE', 'CULTIVAR'])
    stages = pf.stage_summary(df, ['SITE', 'CULTIVAR'])
    return shaded, per_year, summary, stages, sites


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(test, shaded, summary, stages, sites):
    fig, axes = pf.panel_grid(len(PANEL_VARS), N_COLS, FIG_HEIGHT_MM, sharey=SHARE_Y, sharex=True)
    shaded = shaded[shaded['SITE'].isin(sites)]
    stages = stages[stages['SITE'].isin(sites) & (stages['CULTIVAR'] == CULTIVAR)]
    used = set()
    x_lim = X_LIM or pf.x_limits(shaded[pf.X_COL])
    for k, (ax, var) in enumerate(zip(axes, PANEL_VARS)):
        for site in sites:
            s = summary[(summary['SITE'] == site) & (summary['VAR'] == var)]
            raw = shaded[shaded['SITE'] == site]
            used |= pf.draw_series(ax, s, test, pf.site_color_dict[site], raw=raw, raw_y=pf.pct_col(var),
                                   show_raw=SHOW_RAW, show_ci=SHOW_CI)
        pf.draw_control_line(ax)
        ax.set_xlim(*x_lim)
        pf.format_dd_axis(ax, X_MAJOR, X_MINOR)
        ax.tick_params(axis='x', labelbottom=True)      # x tick labels on every panel, not just the bottom row
        pf.panel_title(ax, k, pf.var_label(var))
        if Y_LIM is None and not SHARE_Y:
            pf.shared_ylim([ax], summary[(summary['VAR'] == var) & summary['SITE'].isin(sites)],
                           include_ci=SHOW_CI, headroom=0.15)
    if Y_LIM is not None or SHARE_Y:
        pf.shared_ylim(axes, summary[summary['SITE'].isin(sites) & summary['VAR'].isin(PANEL_VARS)],
                       Y_LIM, include_ci=SHOW_CI, headroom=0.15)
    for ax in axes:
                pf.draw_stage_ticks(ax, stages, 'SITE', pf.site_color_dict, ticks=SHOW_SITE_TICKS,
                            ranges=SHOW_STAGE_RANGES)

    fig.supylabel(pf.YLABEL_PCT, fontsize=pf.FONT_SIZE_NORMAL)
    pf.figure_legend(fig, [
        ('Site', pf.handles_sites(sites)),
        (pf.TEST_SHORT[test].capitalize(), pf.handles_stats(test, used)),
        ('Data', pf.handles_data()),
        ('Growth stage', [h for h in pf.handles_stages(ticks=True, ranges=SHOW_STAGE_RANGES)
                          if SHOW_SITE_TICKS or h.get_label() != 'Mean stage per site (tick colour)']),
    ], xlabel=pf.XLABEL_DD)
    return fig


def main():
    start = pf.start_script(__file__)
    shaded, per_year, summary, stages, sites = prepare()
    for test in pf.TESTS:
        fig = make_figure(test, shaded, summary, stages, sites)
        pf.save(fig, f'{FILE_BASE}_{test}')
        pf.save_table(pf.significant_windows(summary, test, ['SITE', 'CULTIVAR']).round(0),
                      f'{FILE_BASE}_{test}_significant_windows')
    pf.save_table(summary, f'{FILE_BASE}_bin_summary_tests')
    pf.save_table(per_year, f'{FILE_BASE}_per_year_bins')
    pf.save_table(stages, f'{FILE_BASE}_growth_stages_dd')
    pf.print_stage_caption()
    pf.finish_script(start)


if __name__ == '__main__':
    main()
