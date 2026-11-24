#!/usr/bin/env python3
"""
Supplementary figure: observed (Fischer 1985, Expt 74A) vs simulated (APSIM NextGen)
reduction in grain number for each shading timing in the experiment.

One panel per site plus an 'All sites' panel. Each point is one Fischer shading timing:
  x = simulated reduction: mean over years of the APSIM reduction in the pf.DD_BIN_WIDTH °Cd
      bin that contains the Fischer timing (bins with < pf.MIN_YEARS years are left out)
  y = observed reduction from the digitised Fischer data
  reduction (pp) = 100 - grain number as % of the same-year unshaded control
  colour = thermal time from anthesis to the middle of the shading period (°Cd)
Lines: 1:1 line (dashed); regression of observed on simulated (solid, Piñeiro et al. 2008)
with its 95% confidence band (t distribution, n - 2 df).
'All sites' = mean of the sites within each year, then the mean over years.

Run from the command line:
    python fig_s_fischer_apsim_observed_vs_simulated.py
Shared settings (fonts, sizes, colours, saving) are in paper_1_functions.py.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402
import matplotlib as mpl                  # noqa: E402
import matplotlib.lines as mlines         # noqa: E402
import matplotlib.patches as mpatches     # noqa: E402
from scipy import stats                   # noqa: E402

SCRIPTS_BASE = Path(__file__).resolve().parents[1]
if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg             # noqa: E402
import paper_1_functions as pf            # noqa: E402

# ══════════════════════════ SETTINGS ══════════════════════════
# Fischer (1985) digitised data and weather: stored with the scripts
FISCHER_DIR = Path(cfg.ANALYSIS_DATA_FILES_IN_SCRIPTS_DIR)

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
RESPONSE = 'GRAIN_NUMBER_MATURITY'

FISCHER_WEATHER_FILE = 'fischer_1985_daily_temp_radiation.csv'   # daily weather (accumulated °Cd)
FISCHER_GRAIN_FILE = 'fischer_grain_number_data.csv'             # digitised grain-number points
FISCHER_ANTHESIS_DAS = 86      # days after sowing to 50% anthesis (Fischer 1975, p. 610)
FISCHER_LABEL = 'Expt 74A'

FILE_BASE = 'supp_figure_1_simulated_vs_expt74_regressions'
SAVE_TABLE = False             # True = also save the matched points and regression results (CSV)

INCLUDE_ALL_SITES = True       # True = add an 'All sites' panel after the site panels
N_COLS = 3
PANEL_MM = 58                  # height of one row of panels
LEGEND_MM = 22                 # space for the x label and legend below the panels
AXIS_LIM = None                # e.g. (-5, 40) on both axes; None = data range of all panels, rounded out to TICK_STEP
TICK_STEP = None               # tick spacing (pp) on both axes, e.g. 10; None = automatic

SHOW_BAND = True               # 95% confidence band of the regression line
SHOW_N = False                 # True = add n (number of Fischer timings) to the statistics box
POINT_SIZE = 16                # marker area (pt²)
BAND_COLOR = '#D9D9D9'         # solid (EPS cannot store transparency)
FIT_COLOR = 'black'
ONE_TO_ONE_STYLE = {'color': pf.CONTROL_LINE_STYLE['color'], 'linestyle': '--', 'linewidth': pf.LW_THIN}

X_LABEL = 'Simulated reduction in grain number, APSIM NextGen (pp)'
Y_LABEL = f'Observed reduction in grain number, {FISCHER_LABEL} (pp)'
CBAR_LABEL = pf.XLABEL_DD.replace(' to middle', '\nto middle')
ALL_LABEL = 'All sites'


# ══════════════════════════ DATA ══════════════════════════
def load_fischer():
    """Fischer timings: thermal time from anthesis (°Cd) and observed reduction (pp)."""
    weather = pd.read_csv(FISCHER_DIR / FISCHER_WEATHER_FILE)
    anth = weather.loc[weather['DAS'] == FISCHER_ANTHESIS_DAS, 'ACCUMULATED_TEMP']
    if len(anth) != 1:
        raise ValueError(f'Expected one weather row for DAS {FISCHER_ANTHESIS_DAS}, found {len(anth)}')
    grain = pd.read_csv(FISCHER_DIR / FISCHER_GRAIN_FILE)
    grain['DAS'] = grain['DAYS_AFTER_SOWING'].round(0).astype('int64')
    dup = grain.loc[grain['DAS'].duplicated(), 'DAS'].tolist()
    if dup:
        raise ValueError(f'{FISCHER_GRAIN_FILE}: several points round to the same day {dup}')
    f = grain.merge(weather[['DAS', 'ACCUMULATED_TEMP']], on='DAS', how='left', validate='one_to_one')
    if f['ACCUMULATED_TEMP'].isna().any():
        raise ValueError(f'No weather row for DAS {f.loc[f["ACCUMULATED_TEMP"].isna(), "DAS"].tolist()}')
    f = f.dropna(subset=['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL'])
    out = pd.DataFrame({'FISCHER_DD': f['ACCUMULATED_TEMP'] - anth.iloc[0],
                        'OBS_REDUCTION': 100 - f['GRAIN_NUMBER_PERCENT_UNSHADED_CONTROL']})
    out = out.sort_values('FISCHER_DD').reset_index(drop=True)
    out['DD_BIN'] = pf.dd_bin(out['FISCHER_DD']).round(6)
    print(f'Fischer: {len(out)} timings, {out["FISCHER_DD"].min():.0f} to {out["FISCHER_DD"].max():.0f} °Cd '
          f'from anthesis (anthesis = {anth.iloc[0]:.0f} °Cd after sowing)')
    return out


APSIM_COLUMNS = ['SITE', 'CULTIVAR', pf.YEAR_COL, 'VARIABLE', 'SHIFT_DOY', 'END_SHADING_DOY', 'DOY_MATURITY',
                 RESPONSE, pf.DD_ANTHESIS_COL, pf.dd_shading_col()]


def load_apsim():
    """Per site x year x °Cd bin: mean simulated reduction (pp) of that year's shading windows."""
    df = pf.load_parquet(APSIM_FILE, APSIM_COLUMNS, filters={'CULTIVAR': CULTIVAR})
    df = pf.drop_after_maturity(df, end_col='END_SHADING_DOY', maturity_col='DOY_MATURITY')
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, [RESPONSE]))
    sites = [s for s in pf.site_order if s in set(shaded['SITE'])]
    others = sorted(set(shaded['SITE']) - set(pf.site_order))
    if others:
        print(f'Sites not in pf.site_order (not plotted): {others}')
    per_year = pf.bin_per_year(shaded[shaded['SITE'].isin(sites)], [pf.pct_col(RESPONSE)], ['SITE'])
    per_year['SIM_REDUCTION'] = 100 - per_year['PCT']
    per_year['DD_BIN'] = per_year['DD_BIN'].round(6)
    print(f'APSIM {CULTIVAR}: {len(sites)} sites {sites}, {per_year[pf.YEAR_COL].nunique()} years')
    return per_year, sites


def year_by_bin(per_year):
    """Year x bin table of simulated reduction; bins with < pf.MIN_YEARS years are blanked."""
    wide = per_year.pivot_table(index=pf.YEAR_COL, columns='DD_BIN', values='SIM_REDUCTION', aggfunc='mean')
    wide.loc[:, wide.notna().sum() < pf.MIN_YEARS] = np.nan
    return wide


def match_points(fischer, per_year, groups):
    """One row per group x Fischer timing: observed and mean simulated reduction (with t CI)."""
    curves = {site: year_by_bin(g) for site, g in per_year.groupby('SITE')}
    if 'ALL' in groups:   # mean of the sites within each year (sites weighted equally)
        curves['ALL'] = year_by_bin(per_year.groupby([pf.YEAR_COL, 'DD_BIN'], as_index=False)['SIM_REDUCTION'].mean())
    rows = []
    for g in groups:
        w = curves[g]
        for _, f in fischer.iterrows():
            v = w[f['DD_BIN']] if f['DD_BIN'] in w.columns else pd.Series(dtype=float)
            mean, lo, hi, n, _ = pf.t_ci(v)
            rows.append({'SITE': g, 'FISCHER_DD': f['FISCHER_DD'], 'DD_BIN': f['DD_BIN'],
                         'OBS_REDUCTION': f['OBS_REDUCTION'], 'SIM_REDUCTION': mean,
                         'SIM_CI_LOW': lo, 'SIM_CI_HIGH': hi, 'N_YEARS': n})
    matched = pd.DataFrame(rows)
    dropped = matched[matched['SIM_REDUCTION'].isna()]
    for g, d in dropped.groupby('SITE', sort=False):
        print(f'WARNING {g}: Fischer timings with no simulated bin (< {pf.MIN_YEARS} years), '
              f'left out: {", ".join(f"{x:.0f}" for x in d["FISCHER_DD"])} °Cd')
    return matched


def regression(x, y):
    """observed = a + b * simulated (ordinary least squares, Piñeiro et al. 2008)."""
    r = stats.linregress(x, y)
    n = len(x)
    t = stats.t.ppf(0.5 + pf.CI_LEVEL / 2, n - 2)
    return {'N': n, 'SLOPE': r.slope, 'INTERCEPT': r.intercept, 'R2': r.rvalue ** 2,
            'SLOPE_CI_LOW': r.slope - t * r.stderr, 'SLOPE_CI_HIGH': r.slope + t * r.stderr,
            'INTERCEPT_CI_LOW': r.intercept - t * r.intercept_stderr,
            'INTERCEPT_CI_HIGH': r.intercept + t * r.intercept_stderr, 'P_SLOPE': r.pvalue}


def confidence_band(x, y, fit, x_line):
    """Fitted line and its CI_LEVEL confidence band (t, n - 2 df)."""
    n = len(x)
    y_hat = fit['INTERCEPT'] + fit['SLOPE'] * x_line
    s = np.sqrt(np.sum((y - (fit['INTERCEPT'] + fit['SLOPE'] * x)) ** 2) / (n - 2))
    se = s * np.sqrt(1 / n + (x_line - x.mean()) ** 2 / np.sum((x - x.mean()) ** 2))
    half = stats.t.ppf(0.5 + pf.CI_LEVEL / 2, n - 2) * se
    return y_hat, y_hat - half, y_hat + half


def axis_limits(matched):
    """One range and one tick spacing for BOTH axes of every panel. Without AXIS_LIM the range
    covers the observed and simulated values of all panels, rounded out to whole ticks."""
    v = matched[['OBS_REDUCTION', 'SIM_REDUCTION']].to_numpy(float).ravel()
    lo, hi = AXIS_LIM or (np.nanmin(v), np.nanmax(v))
    step = TICK_STEP or np.diff(mpl.ticker.MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi))[0]
    if not AXIS_LIM:
        lo, hi = np.floor(lo / step) * step, np.ceil(hi / step) * step
    return (lo, hi), step


def stats_text(fit):
    intercept = round(fit['INTERCEPT'], 1) + 0.0   # + 0.0 so -0.0 prints as 0.0
    lines = [f'Slope = {fit["SLOPE"]:.2f}', f'Intercept = {intercept:.1f} pp', f'$R^2$ = {fit["R2"]:.2f}']
    if SHOW_N:
        lines.append(f'n = {fit["N"]}')
    return '\n'.join(lines).replace('-', '−')


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(matched, groups):
    n_rows = int(np.ceil(len(groups) / N_COLS))
    height = min(pf.MAX_FIG_HEIGHT_MM, n_rows * PANEL_MM + LEGEND_MM)
    fig, axes = pf.panel_grid(len(groups), N_COLS, height, sharey=True, sharex=True)
    lims, step = axis_limits(matched)
    x_line = np.linspace(*lims, 200)
    norm = mpl.colors.Normalize(matched['FISCHER_DD'].min(), matched['FISCHER_DD'].max())
    fits = []
    for k, (ax, g) in enumerate(zip(axes, groups)):
        d = matched[matched['SITE'] == g].dropna(subset=['OBS_REDUCTION', 'SIM_REDUCTION'])
        x, y = d['SIM_REDUCTION'].to_numpy(float), d['OBS_REDUCTION'].to_numpy(float)
        ax.plot(lims, lims, zorder=2, **ONE_TO_ONE_STYLE)
        if len(x) >= 3:
            fit = regression(x, y)
            fits.append({'SITE': g, **fit})
            y_hat, lo, hi = confidence_band(x, y, fit, x_line)
            if SHOW_BAND:
                ax.fill_between(x_line, lo, hi, color=BAND_COLOR, linewidth=0, zorder=1)
            ax.plot(x_line, y_hat, color=FIT_COLOR, linewidth=pf.LW_MED, zorder=3)
            ax.text(0.04, 0.96, stats_text(fit), transform=ax.transAxes, va='top', ha='left',
                    fontsize=pf.FONT_SIZE_SMALL, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='black',
                              linewidth=pf.LW_THIN))
        else:
            ax.text(0.5, 0.5, f'n = {len(x)}', transform=ax.transAxes, ha='center', va='center')
        ax.scatter(x, y, c=d['FISCHER_DD'], cmap=pf.DD_CMAP, norm=norm, s=POINT_SIZE,
                   edgecolors='black', linewidths=pf.LW_THIN, zorder=4)
        for axis in (ax.xaxis, ax.yaxis):          # identical range and ticks on x and y
            axis.set_major_locator(mpl.ticker.MultipleLocator(step))
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_aspect('equal', adjustable='box')  # square panels: 1 pp is the same length on both axes
        ax.tick_params(axis='x', labelbottom=True)
        pf.panel_title(ax, k, ALL_LABEL if g == 'ALL' else pf.format_site_name(g))

    cbar = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=pf.DD_CMAP), ax=axes, location='right',
                        shrink=0.5, aspect=30)
    cbar.set_label(CBAR_LABEL, fontsize=pf.FONT_SIZE_SMALL)
    cbar.ax.tick_params(labelsize=pf.FONT_SIZE_SMALL)
    cbar.outline.set_linewidth(pf.LW_THIN)

    fig.supylabel(Y_LABEL, fontsize=pf.FONT_SIZE_NORMAL)
    handles = [mlines.Line2D([], [], label='1:1 line', **ONE_TO_ONE_STYLE),
               mlines.Line2D([], [], color=FIT_COLOR, linewidth=pf.LW_MED, label='Fitted regression')]
    if SHOW_BAND:
        handles.append(mpatches.Patch(facecolor=BAND_COLOR, edgecolor='none',
                                      label=f'{pf.CI_LEVEL:.0%} confidence band'))
    pf.figure_legend(fig, [(None, [h]) for h in handles], xlabel=X_LABEL)
    return fig, pd.DataFrame(fits)


def main():
    start = pf.start_script(__file__)
    fischer = load_fischer()
    per_year, sites = load_apsim()
    groups = sites + (['ALL'] if INCLUDE_ALL_SITES else [])
    matched = match_points(fischer, per_year, groups)
    fig, fits = make_figure(matched, groups)
    pf.save(fig, FILE_BASE)
    with pd.option_context('display.width', 200, 'display.float_format', '{:.2f}'.format):
        print(fits[['SITE', 'N', 'SLOPE', 'SLOPE_CI_LOW', 'SLOPE_CI_HIGH', 'INTERCEPT', 'R2']].to_string(index=False))
    if SAVE_TABLE:
        pf.save_table(matched.round(3), f'{FILE_BASE}_matched_points')
        pf.save_table(fits.round(4), f'{FILE_BASE}_regression')
    pf.finish_script(start)


if __name__ == '__main__':
    main()