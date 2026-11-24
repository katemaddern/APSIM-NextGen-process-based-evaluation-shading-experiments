#!/usr/bin/env python3
"""
Figure 7: grain number by cultivar. One panel per cultivar, one marker colour per site
(pf.site_color_dict), with the critical-period definitions as horizontal bars below the data.

x  = thermal time (°Cd) from anthesis to the middle of the shading window
y  = grain number, % of the same-site, same-cultivar, same-year unshaded control
Points: light = every shaded simulation; bars = 95% CI (t, n - 1 df, n = years);
markers = mean across years per DD_BIN_WIDTH °Cd bin, filled if significantly different
from the control (Holm-adjusted). One figure per test (pf.TESTS).
Growth stages: each site's mean stage for that cultivar is a tick in the site colour at the
top of the panel; anthesis is a full line. Critical-period bars: mean start and end over
the shaded runs of that cultivar, pooled across sites and years.

Run from the command line:
    python fig_5_cultivar_by_site_gn_with_defs_bars.py
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


VAR = 'GRAIN_NUMBER_MATURITY'
Y_LABEL = f'{pf.var_label(VAR)} (% of unshaded control)'
FILE_BASE = 'figure_6_all_cultivars_all_sites'

N_COLS = 3                    # 3 columns -> 4 rows for 12 cultivars
FIG_HEIGHT_MM = pf.MAX_FIG_HEIGHT_MM
Y_LIM = (58, 110)             # None = automatic (same on every panel)
X_LIM = None                  # e.g. (-800, 600) for every panel; None = each panel's data + CP bars
X_MAJOR, X_MINOR = pf.DD_MAJOR, pf.DD_MINOR  # °Cd tick spacing (labelled, unlabelled): panels are narrow
SHOW_RAW = False          # True = light background points for every simulation
SHOW_CI = True
SHOW_SITE_TICKS = False   # True = a tick in each site's colour at the top for that site's mean stage
SHOW_STAGE_RANGES = True 

SHOW_CP = True
CP_Y_BOTTOM = 60              # y of the lowest critical-period bar
CP_Y_STEP = 1.5               # % units between bars


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    # critical-period columns are read if present (definitions missing from the file are skipped)
    df = pf.load_shading_data(DATA_PATH, [VAR], optional=pf.crit_period_columns())
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, [VAR]))
    sites = [s for s in pf.site_order if s in set(shaded['SITE'])]
    cultivars = [c for c in pf.cultivar_order if c in set(shaded['CULTIVAR'])]
    skipped = sorted(set(shaded['CULTIVAR']) - set(pf.cultivar_order))
    if skipped:
        print('In data but not in pf.cultivar_order (not plotted):', skipped)
    print(f'{len(cultivars)} cultivars, {len(sites)} sites {sites}')
    per_year, summary = pf.summarise_shading(shaded, [VAR], ['SITE', 'CULTIVAR'])
    stages = pf.stage_summary(df, ['SITE', 'CULTIVAR'])
    cp = pf.cp_summary(shaded, ['CULTIVAR'])
    return shaded, per_year, summary, stages, cp, sites, cultivars


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(test, shaded, summary, stages, cp, sites, cultivars):
    fig, axes = pf.panel_grid(len(cultivars), N_COLS, FIG_HEIGHT_MM, sharey=True)
    used = set()
    for k, (ax, cv) in enumerate(zip(axes, cultivars)):
        x = []
        for site in sites:
            s = summary[(summary['SITE'] == site) & (summary['CULTIVAR'] == cv)]
            raw = shaded[(shaded['SITE'] == site) & (shaded['CULTIVAR'] == cv)]
            used |= pf.draw_series(ax, s, test, pf.site_color_dict[site], raw=raw, raw_y=pf.pct_col(VAR),
                                   show_raw=SHOW_RAW, show_ci=SHOW_CI)
            x += list(s['X_MEAN'])
        cp_cv = cp[cp['CULTIVAR'] == cv]
        if SHOW_CP:
            x += list(cp_cv['START']) + list(cp_cv['END'])
        pf.draw_control_line(ax)
        ax.set_xlim(*(X_LIM or pf.x_limits(x)))
        pf.format_dd_axis(ax, X_MAJOR, X_MINOR)
        ax.tick_params(axis='x', labelsize=pf.FONT_SIZE_SMALL)
        pf.panel_title(ax, k, pf.format_cultivar_name(cv))

    pf.shared_ylim(axes, summary[summary['SITE'].isin(sites)], Y_LIM, include_ci=SHOW_CI, headroom=0.15)
    if SHOW_CP:
        y_pos = pf.cp_bar_positions(CP_Y_BOTTOM, CP_Y_STEP)
        lo, hi = axes[0].get_ylim()
        for ax in axes:
            ax.set_ylim(min(lo, CP_Y_BOTTOM - CP_Y_STEP), hi)
        for ax, cv in zip(axes, cultivars):
            pf.draw_cp_bars(ax, cp[cp['CULTIVAR'] == cv], y_pos)
    for ax, cv in zip(axes, cultivars):
        pf.draw_stage_ticks(ax, stages[stages['CULTIVAR'] == cv], 'SITE', pf.site_color_dict,
                            ticks=SHOW_SITE_TICKS, ranges=SHOW_STAGE_RANGES)

    fig.supylabel(Y_LABEL, fontsize=pf.FONT_SIZE_NORMAL)
    groups = [('Site', pf.handles_sites(sites)),
              (pf.TEST_SHORT[test].capitalize(), pf.handles_stats(test, used)),
              ('Data', pf.handles_data()),
              ('Growth stage', [h for h in pf.handles_stages(ticks=True, ranges=SHOW_STAGE_RANGES)
                          if SHOW_SITE_TICKS or h.get_label() != 'Mean stage per site (tick colour)']),]
    if SHOW_CP:
        groups.append(('Critical period', pf.handles_cp(cp['DEFINITION'])))
    pf.figure_legend(fig, groups, xlabel=pf.XLABEL_DD, fontsize=7, columnspacing=0.8)
    return fig


def main():
    start = pf.start_script(__file__)
    shaded, per_year, summary, stages, cp, sites, cultivars = prepare()
    for test in pf.TESTS:
        fig = make_figure(test, shaded, summary, stages, cp, sites, cultivars)
        pf.save(fig, f'{FILE_BASE}_{test}')
        pf.save_table(pf.significant_windows(summary, test, ['SITE', 'CULTIVAR']).round(0),
                      f'{FILE_BASE}_{test}_significant_windows')
    pf.save_table(summary, f'{FILE_BASE}_bin_summary_tests')
    pf.save_table(per_year, f'{FILE_BASE}_per_year_bins')
    pf.save_table(stages, f'{FILE_BASE}_growth_stages_dd')
    pf.save_table(cp.round(1), f'{FILE_BASE}_critical_period_definitions_dd')
    pf.print_stage_caption()
    pf.finish_script(start)


if __name__ == '__main__':
    main()
