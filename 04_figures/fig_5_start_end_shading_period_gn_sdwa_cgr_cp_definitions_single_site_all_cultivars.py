#!/usr/bin/env python3
"""
Figure 6: critical-period timing by cultivar at one site (cfg.EXAMPLE_SITE).
One panel per cultivar; everything on the x axis is thermal time (°Cd) from anthesis.

x  = thermal time from anthesis to the FIRST (circles) and LAST (squares) day of the
     shading window, binned separately
y  = % of the same-site, same-cultivar, same-year unshaded control
Colour = variable (pf.VARIABLE_STYLES). Points: light = every shaded simulation;
bars = 95% CI (t, n - 1 df, n = years); markers = mean across years per DD_BIN_WIDTH °Cd bin.
No significance testing: the marker fill shows the shading point (POINT_FILLED; default
first day of shading = hollow circles, last day = filled squares). Bins with fewer than
pf.MIN_YEARS years are not drawn.
Growth stages: mean of that cultivar at this site. Critical-period definitions: bars below
the data (mean start and end over the shaded runs).

Run from the command line:
    python fig_6_cp_timing_cultivar_comparison_degree_days.py
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

SITE = cfg.EXAMPLE_SITE
FILE_BASE = f'figure_5_single_site_{SITE}_by_all_cultivars'

# Summarised and tested: all of these. Drawn (back to front): PLOT_VARS.
RAW_VARS = [
    'GRAIN_NUMBER_MATURITY',
    'SPIKE_WEIGHT_ANTHESIS_STAGE',
    'DURATION_CRITICAL_PERIOD',
    'CROP_GROWTH_RATE_CRITICAL_PERIOD',
    'PARTITIONING_TO_SPIKE_CRITICAL_PERIOD',
    'FRUITING_EFFICIENCY_CRITICAL_PERIOD',
]
PLOT_VARS = [
    'CROP_GROWTH_RATE_CRITICAL_PERIOD',
    'SPIKE_WEIGHT_ANTHESIS_STAGE',
    'GRAIN_NUMBER_MATURITY',
]
# Shading-window points shown, with their marker and whether the marker is filled
POINTS = {'START': 'o', 'END': 's'}
POINT_FILLED = {'START': False, 'END': True}     # False = hollow (white face, coloured edge)
POINT_LABELS = {'START': 'First day of shading', 'MID': 'Middle of shading', 'END': 'Last day of shading'}

N_COLS = 3                    # 3 columns -> 4 rows for 12 cultivars
FIG_HEIGHT_MM = pf.MAX_FIG_HEIGHT_MM
Y_LIM = None                  # e.g. (40, 130); None = automatic (same on every panel)
X_BUFFER = 150                 # °Cd before the earliest CP start and after the latest CP end
# X_MAJOR, X_MINOR = pf.DD_MAJOR, pf.DD_MINOR 
X_MAJOR, X_MINOR = 300, pf.DD_MINOR 
SHOW_RAW = True
SHOW_CI = True
MIN_YEARS = pf.MIN_YEARS      # bins with fewer years than this are not drawn

CP_Y_BOTTOM = None            # y of the lowest critical-period bar; None = below the data
CP_Y_STEP = 2.5               # % units between bars
CP_Y_GAP = 3                  # % units between the data and the top bar (CP_Y_BOTTOM = None)


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    df = pf.load_shading_data(DATA_PATH, RAW_VARS, filters={'SITE': SITE}, points=list(POINTS),
                              optional=pf.crit_period_columns())
    shaded = pf.percent_of_control(df, RAW_VARS)
    for p in POINTS:
        pf.add_dd_from_anthesis(shaded, point=p, out_col=f'DD_{p}')
    cultivars = [c for c in pf.cultivar_order if c in set(shaded['CULTIVAR'])]
    print(f'{SITE}: {len(cultivars)} cultivars {cultivars}')
    per_year, summary = [], []
    for p in POINTS:
        py = pf.bin_per_year(shaded, [pf.pct_col(v) for v in RAW_VARS], ['SITE', 'CULTIVAR'], x_col=f'DD_{p}')
        s = bin_means(py, ['SITE', 'CULTIVAR'])
        py['POINT'], s['POINT'] = p, p
        per_year.append(py)
        summary.append(s)
    stages = pf.stage_summary(df, ['SITE', 'CULTIVAR'])
    cp = pf.cp_summary(shaded, ['CULTIVAR'])
    return shaded, pd.concat(per_year), pd.concat(summary), stages, cp, cultivars


def bin_means(per_year, group_cols):
    """Mean and 95% CI (t, n - 1 df, n = years) per group x VAR x DD_BIN. No significance tests."""
    keys = list(group_cols) + ['VAR', 'DD_BIN']
    rows = []
    for k, g in per_year.groupby(keys, sort=True):
        mean, lo, hi, n, sd = pf.t_ci(g['PCT'])
        rows.append({**dict(zip(keys, k)), 'X_MEAN': g['X'].mean(), 'MEAN': mean, 'SD': sd,
                     'CI_LOW': lo, 'CI_HIGH': hi, 'N_YEARS': n})
    return pd.DataFrame(rows)


def draw_means(ax, s, color, marker, filled):
    """95% CI bars and bin means; hollow or filled marker."""
    s = s[s['N_YEARS'] >= MIN_YEARS].sort_values('X_MEAN')
    if SHOW_CI:
        pf.draw_ci(ax, s['X_MEAN'], s['CI_LOW'], s['CI_HIGH'], color)
    ax.scatter(s['X_MEAN'], s['MEAN'], s=pf.STAT_SIZE, marker=marker,
               facecolor=color if filled else 'white', edgecolor=color,
               linewidths=pf.STAT_EDGE_WIDTH, zorder=pf.Z_STAT)


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(shaded, summary, stages, cp, cultivars):
    fig, axes = pf.panel_grid(len(cultivars), N_COLS, FIG_HEIGHT_MM, sharey=True)
    for k, (ax, cv) in enumerate(zip(axes, cultivars)):
        raw = shaded[shaded['CULTIVAR'] == cv]
        for var in PLOT_VARS:
            for p, marker in POINTS.items():
                if SHOW_RAW:
                    pf.draw_raw(ax, raw[f'DD_{p}'], raw[pf.pct_col(var)], pf.var_color(var))
                s = summary[(summary['CULTIVAR'] == cv) & (summary['VAR'] == var) & (summary['POINT'] == p)]
                draw_means(ax, s, pf.var_color(var), marker, POINT_FILLED[p])
        pf.draw_control_line(ax)
        cp_cv = cp[cp['CULTIVAR'] == cv]
        if len(cp_cv):
            ax.set_xlim(cp_cv['START'].min() - X_BUFFER, cp_cv['END'].max() + X_BUFFER)
        else:
            print(f'{cv}: no CP definitions found, x limits from the data')
            ax.set_xlim(*pf.x_limits(summary.loc[summary['CULTIVAR'] == cv, 'X_MEAN']))
        pf.format_dd_axis(ax, X_MAJOR, X_MINOR)
        ax.tick_params(axis='x', labelsize=pf.FONT_SIZE_SMALL)
        pf.panel_title(ax, k, pf.format_cultivar_name(cv))

    shown = summary[summary['VAR'].isin(PLOT_VARS) & (summary['N_YEARS'] >= MIN_YEARS)]
    lo, hi = pf.shared_ylim(axes, shown, Y_LIM, include_ci=SHOW_CI, headroom=0.15)
    n_cp = len(pf.cp_definition_order)
    bottom = CP_Y_BOTTOM if CP_Y_BOTTOM is not None else lo - CP_Y_GAP - (n_cp - 1) * CP_Y_STEP
    for ax in axes:
        ax.set_ylim(min(lo, bottom - CP_Y_STEP), hi)
    y_pos = pf.cp_bar_positions(bottom, CP_Y_STEP)
    for ax, cv in zip(axes, cultivars):
        pf.draw_cp_bars(ax, cp[cp['CULTIVAR'] == cv], y_pos)
        pf.draw_stages(ax, pf.stages_for(stages, SITE=SITE, CULTIVAR=cv))

    fig.supylabel(pf.YLABEL_PCT, fontsize=pf.FONT_SIZE_NORMAL)
    point_handles = [pf.handle_marker(POINT_LABELS[p], marker=m, edge='#4D4D4D',
                                      face='#4D4D4D' if POINT_FILLED[p] else 'white')
                     for p, m in POINTS.items()]
    data_handles = pf.handles_data()
    if not SHOW_RAW:
        data_handles = data_handles[1:]                 # no 'Individual simulations' entry
    pf.figure_legend(fig, [
        ('Variable', pf.handles_variables(PLOT_VARS[::-1])),
        ('Shading point', point_handles),
        ('Data', data_handles),
        ('Growth stage', pf.handles_stages()),
        ('Critical period', pf.handles_cp(cp['DEFINITION'])),
    ], xlabel='Thermal time from anthesis to the first or last day of the shading period (°Cd)',
        fontsize=7, columnspacing=0.8)
    return fig


def main():
    start = pf.start_script(__file__)
    shaded, per_year, summary, stages, cp, cultivars = prepare()
    pf.save(make_figure(shaded, summary, stages, cp, cultivars), FILE_BASE)
    pf.save_table(summary, f'{FILE_BASE}_bin_means')
    pf.save_table(per_year, f'{FILE_BASE}_per_year_bins')
    pf.save_table(stages, f'{FILE_BASE}_growth_stages_dd')
    pf.save_table(cp.sort_values(['CULTIVAR', 'DURATION']).round(1), f'{FILE_BASE}_critical_period_definitions_dd')
    pf.print_stage_caption()
    pf.finish_script(start)


if __name__ == '__main__':
    main()