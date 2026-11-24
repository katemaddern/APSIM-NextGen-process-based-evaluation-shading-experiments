#!/usr/bin/env python3
"""
Figure 4: relationships between yield components under shading, all sites pooled, for one
cultivar (cfg.EXAMPLE_CULTIVAR), using the shading windows whose WINDOW_POINT (first day,
middle or last day of shading; default: last day) falls between WINDOW_FROM and WINDOW_TO
(default: flag leaf appearance and anthesis, inclusive). With WINDOW_POINT = 'END' every
window used has finished by anthesis. Every point is one shaded simulation, coloured by the
timing of the shading in thermal time (°Cd from anthesis to the middle of the shading window).

One figure (figure_4), 2 x 2 grid: three relationships (PANELS) and the shared colour bar in
the fourth position (with four panels the colour bar goes below them instead):
  (a) spike dry weight at anthesis ~ crop growth rate
  (b) grain number ~ spike dry weight at anthesis
  (c) fruiting efficiency ~ spike dry weight at anthesis
Each panel: Theil–Sen line (median of all pairwise slopes: the slope estimator that goes with
Kendall's tau, robust to heteroscedasticity and outliers), with a box giving the labelled
Theil–Sen equation ('Theil–Sen: y = bx + a') and Kendall's tau-b. Significance stars
(SHOW_STARS) and the number of simulations and site-years (SHOW_N) are off by default; both
are in figure_4_relationships.csv for the caption.

Relationship statistics (figure_4_relationships.csv), all from the actual data, no resampling:
  Theil–Sen    slope (95% CI from the Kendall statistic, Sen 1968), intercept
               (median of y - slope*x) and descriptive R² of the line (1 - SS_res/SS_tot)
  Kendall      tau-b and its p value, Holm-adjusted across the panels
  OLS          slope and intercept with 95% CIs and p from cluster-robust standard errors
               (clusters = site-years), and R²; p Holm-adjusted across the panels
  counts       simulations, years and site-years
NOTE: the Theil–Sen CI and the Kendall p treat every simulation as independent. Simulations
from the same site-year share weather, so these are optimistic; the cluster-robust OLS CIs
are the ones that allow for it.

Linear-regression assumption checks (every panel), saved as
figure_4_regression_assumptions.csv and printed:
  normality of residuals   Shapiro–Wilk (D'Agostino K² when n > 5000); plus skew and kurtosis
  constant variance        Breusch–Pagan
  linearity                Ramsey RESET (adds fitted² to the model)
  independence             Durbin–Watson, residuals ordered by site, year, then shading timing
                           (consecutive shading dates in the same year are near-replicates)
  influential points       number of points with Cook's distance > 4/n
Plus diagnostic plots (residuals vs fitted, normal Q-Q, scale-location):
figure_4_regression_diagnostics.

Run from the command line:
    python fig_3_sdwa_gn_sdwa_cgr_correlations_all_sites.py
Shared settings (colours, labels, fonts, colour map) are in paper_1_functions.py.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
import matplotlib as mpl                 # noqa: E402
import matplotlib.pyplot as plt          # noqa: E402
from scipy import stats                  # noqa: E402
import statsmodels.api as sm             # noqa: E402
from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset  # noqa: E402
from statsmodels.stats.stattools import durbin_watson                    # noqa: E402

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
FILE_BASE = f'figure_3_all_sites_{CULTIVAR}'

# Panels, in order (a), (b), (c): (x variable, y variable, same limits on both axes)
PANELS = [
    ('CROP_GROWTH_RATE_CRITICAL_PERIOD', 'SPIKE_WEIGHT_ANTHESIS_STAGE', False),
    ('SPIKE_WEIGHT_ANTHESIS_STAGE', 'GRAIN_NUMBER_MATURITY', True),
    ('SPIKE_WEIGHT_ANTHESIS_STAGE', 'FRUITING_EFFICIENCY_CRITICAL_PERIOD', False),
]
VARS = list(dict.fromkeys(v for xv, yv, _ in PANELS for v in (xv, yv)))   # every variable in PANELS

# Shading windows used: WINDOW_POINT of the window falls from this stage ...
WINDOW_FROM, WINDOW_TO = 'FLAG_LEAF', 'ANTHESIS_STAGE'    # ... to this stage (inclusive)
WINDOW_POINT = 'END'    # point of the shading window that must fall between WINDOW_FROM and WINDOW_TO:
                        # 'START' = first day (original rule), 'MID' = middle, 'END' = last day
CBAR_LABEL = 'Thermal time from anthesis to middle of shading period (°Cd)'

# Figure layout
N_COLS = 2
FIG_HEIGHT_MM = 190                  # 2 x 2 grid, 190 mm wide (use ~205 with four panels + colour bar below)
MARKER_SIZE = 6
CBAR_WIDTH = 0.8                     # colour bar length (fraction of the empty panel's width, or of the
                                     # panels' width when the colour bar goes below)

# Fitted lines and relationship statistics
CI_LEVEL = pf.CI_LEVEL               # 95% confidence intervals
TS_LABEL = 'Theil–Sen'                # label of the fitted-line equation in each panel
TAU_LABEL = "Kendall's τ"            # label of the rank correlation in each panel
SHOW_STARS = False                   # True = significance stars after tau (Holm-adjusted Kendall p)
SHOW_N = False                       # True = 'n = simulations (site-years)' line in each box
TS_CHUNK = 1000                      # rows per block when computing pairwise slopes (lower = less memory)

# Regression assumption checks
ASSUMPTION_ALPHA = pf.ALPHA          # p below this = assumption rejected
DW_OK = (1.5, 2.5)                   # Durbin–Watson range treated as 'no strong autocorrelation'
MIN_N_ASSUMPTIONS = 8                # fewer points than this: checks not run


def axis_label(var, wrap=False):
    sep = '\n' if wrap else ' '
    return f'{pf.var_label(var)}{sep}(% of unshaded control)'


def short_name(xv, yv):
    return f'{pf.var_style(yv)["short"]} ~ {pf.var_style(xv)["short"]}'


# ══════════════════════════ DATA ══════════════════════════
def prepare():
    stage_cols = [f'CUM_DEGREE_DAY_{WINDOW_FROM}', f'CUM_DEGREE_DAY_{WINDOW_TO}']
    df = pf.load_shading_data(DATA_PATH, VARS, filters={'CULTIVAR': CULTIVAR},
                              points=list(dict.fromkeys([WINDOW_POINT, pf.SHADING_POINT])), extra=stage_cols)
    shaded = pf.add_dd_from_anthesis(pf.percent_of_control(df, VARS))
    t = shaded[pf.dd_shading_col(WINDOW_POINT)]          # °Cd at the chosen point of each window
    keep = (t >= shaded[stage_cols[0]]) & (t <= shaded[stage_cols[1]])
    d = shaded[keep].copy()
    print(f'{len(d)} shaded runs with {WINDOW_POINT.lower()} of shading between {WINDOW_FROM} and {WINDOW_TO}')
    print(f'Middle of shading in the kept runs: {d[pf.X_COL].min():.0f} to {d[pf.X_COL].max():.0f} °Cd from anthesis')
    print(f'Sites: {[s for s in pf.site_order if s in set(d["SITE"])]}')
    return d


# ══════════════════════════ RELATIONSHIP STATISTICS ══════════════════════════
def p_stars(p):
    return '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ' ns'


def theil_sen(x, y, level=None):
    """
    Exact Theil–Sen estimator on all the data.
    slope     = median of the slopes between every pair of points with different x
    CI        = Sen (1968): order statistics of the pairwise slopes set by the variance of
                Kendall's S (with tie corrections), as in scipy.stats.theilslopes
    intercept = median of (y - slope * x)
    Pairwise slopes are built in blocks of TS_CHUNK rows to limit memory.
    """
    level = level or CI_LEVEL
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    n = len(x)
    parts, j = [], np.arange(n)
    for i0 in range(0, n - 1, TS_CHUNK):
        i1 = min(i0 + TS_CHUNK, n - 1)
        dx = x[None, :] - x[i0:i1, None]
        dy = y[None, :] - y[i0:i1, None]
        keep = (j[None, :] > np.arange(i0, i1)[:, None]) & (dx != 0)
        parts.append(dy[keep] / dx[keep])
    slopes = np.concatenate(parts)
    del parts
    slopes.sort()
    nt = len(slopes)
    slope = slopes[nt // 2] if nt % 2 else 0.5 * (slopes[nt // 2 - 1] + slopes[nt // 2])

    def tie_term(a):
        _, c = np.unique(a, return_counts=True)
        c = c[c > 1].astype(float)
        return np.sum(c * (c - 1) * (2 * c + 5))

    z = stats.norm.ppf(0.5 + level / 2)
    sigma = np.sqrt((n * (n - 1) * (2 * n + 5) - tie_term(x) - tie_term(y)) / 18)
    upper = min(int(np.round((nt + z * sigma) / 2)), nt - 1)
    lower = max(int(np.round((nt - z * sigma) / 2)) - 1, 0)
    intercept = np.median(y - slope * x)
    fitted = intercept + slope * x
    r2 = 1 - np.sum((y - fitted) ** 2) / np.sum((y - y.mean()) ** 2)
    return {'ts_slope': slope, 'ts_slope_ci_low': slopes[lower], 'ts_slope_ci_high': slopes[upper],
            'ts_intercept': intercept, 'ts_r2': r2, 'n_pairwise_slopes': nt}


def ols_cluster(x, y, clusters, level=None):
    """OLS with cluster-robust (sandwich) standard errors: the coefficients are ordinary OLS;
    only the uncertainty allows for heteroscedasticity and for correlation within a cluster."""
    level = level or CI_LEVEL
    X = sm.add_constant(np.asarray(x, dtype=float))
    groups = pd.factorize(pd.Series(clusters))[0]
    res = sm.OLS(np.asarray(y, dtype=float), X).fit(cov_type='cluster', cov_kwds={'groups': groups})
    ci = res.conf_int(alpha=1 - level)
    return {'ols_intercept': res.params[0], 'ols_intercept_ci_low': ci[0, 0], 'ols_intercept_ci_high': ci[0, 1],
            'ols_slope': res.params[1], 'ols_slope_ci_low': ci[1, 0], 'ols_slope_ci_high': ci[1, 1],
            'ols_slope_p_cluster': res.pvalues[1], 'ols_r2': res.rsquared, 'n_clusters': int(groups.max() + 1)}


def relationship_stats(d, xv, yv):
    """Theil–Sen, Kendall and cluster-robust OLS for y on x, all sites pooled."""
    q = d[['SITE', pf.YEAR_COL, pf.pct_col(xv), pf.pct_col(yv)]].dropna()
    x, y = q[pf.pct_col(xv)].to_numpy(), q[pf.pct_col(yv)].to_numpy()
    row = {'relationship': short_name(xv, yv), 'x': xv, 'y': yv, 'n_simulations': len(q),
           'n_sites': q['SITE'].nunique(), 'n_years': q[pf.YEAR_COL].nunique(),
           'n_site_years': len(q[['SITE', pf.YEAR_COL]].drop_duplicates()),
           'x_min': x.min() if len(x) else np.nan, 'x_max': x.max() if len(x) else np.nan}
    if len(q) < 3 or np.unique(x).size < 2:
        row['note'] = 'too few points'
        return row
    tau = stats.kendalltau(x, y)                      # tau-b
    row['kendall_tau'], row['kendall_p'] = tau.statistic, tau.pvalue
    row.update(theil_sen(x, y))
    clusters = q['SITE'].astype(str) + '_' + q[pf.YEAR_COL].astype(str)   # site-year
    row.update(ols_cluster(x, y, clusters))
    return row


def relationship_table(d):
    rows = []
    for xv, yv, _ in PANELS:
        print(f'  {short_name(xv, yv)}')
        rows.append(relationship_stats(d, xv, yv))
    t = pd.DataFrame(rows)
    for col in ['kendall_p', 'ols_slope_p_cluster']:      # Holm across the panels of the figure
        if col in t:
            t[f'{col}_holm'] = pf._holm(t[col])
    return t


def print_relationships(t):
    cols = ['relationship', 'n_simulations', 'n_site_years', 'ts_slope', 'ts_slope_ci_low',
            'ts_slope_ci_high', 'ts_intercept', 'ts_r2', 'kendall_tau', 'kendall_p_holm',
            'ols_slope', 'ols_slope_ci_low', 'ols_slope_ci_high', 'ols_intercept', 'ols_r2',
            'ols_slope_p_cluster_holm']
    with pd.option_context('display.width', 250, 'display.max_columns', 30, 'display.float_format', '{:.3g}'.format):
        print(t[[c for c in cols if c in t]].to_string(index=False))


def draw_fit(ax, r, fmt='{:.2f}', loc=(0.985, 0.95), ha='right', linewidth=pf.LW_MED,
             fontsize=pf.FONT_SIZE_SMALL, one_line=True, show_n=False):
    """Theil–Sen line over the observed x range, with its equation, tau and (optionally) n."""
    if r is None or not np.isfinite(r.get('ts_slope', np.nan)):
        ax.text(0.5, 0.5, 'n < 3', transform=ax.transAxes, ha='center', va='center', fontsize=fontsize)
        return
    xl = np.linspace(r['x_min'], r['x_max'], 100)
    ax.plot(xl, r['ts_intercept'] + r['ts_slope'] * xl, color='black', linewidth=linewidth, linestyle='--', zorder=3)
    sign = '+' if r['ts_intercept'] >= 0 else '-'
    sep = ';  ' if one_line else '\n'
    equation = f'y = {fmt.format(r["ts_slope"])}x {sign} {abs(r["ts_intercept"]):.1f}'.replace('-', '−')
    tau = f'{r["kendall_tau"]:.2f}'.replace('-', '−')
    label = f'{TS_LABEL}: {equation}{sep}{TAU_LABEL} = {tau}'
    if SHOW_STARS:
        label += p_stars(r['kendall_p_holm'])
    if show_n and SHOW_N:
        label += f'\nn = {r["n_simulations"]:,} ({r["n_site_years"]} site-years)'
    ax.text(*loc, label, transform=ax.transAxes, fontsize=fontsize, va='top', ha=ha,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='black', linewidth=pf.LW_THIN))


# ══════════════════════════ FIGURE ══════════════════════════
def make_figure(d, norm, table):
    n_rows = int(np.ceil(len(PANELS) / N_COLS))
    fig = plt.figure(figsize=pf.fig_size('double', height_mm=FIG_HEIGHT_MM), layout='constrained')
    gs = fig.add_gridspec(n_rows, N_COLS)
    axes = []
    for k, (xv, yv, equal) in enumerate(PANELS):
        ax = fig.add_subplot(gs[k // N_COLS, k % N_COLS])
        axes.append(ax)
        p = d[[pf.pct_col(xv), pf.pct_col(yv), pf.X_COL]].dropna()
        ax.scatter(p.iloc[:, 0], p.iloc[:, 1], c=p[pf.X_COL], cmap=pf.DD_CMAP, norm=norm,
                   edgecolor='none', linewidth=0, s=MARKER_SIZE, rasterized=True)
        r = table[(table['x'] == xv) & (table['y'] == yv)]
        draw_fit(ax, r.iloc[0].to_dict() if len(r) else None, fmt='{:.3f}', loc=(0.05, 0.95), ha='left',
                 linewidth=pf.LW_THICK, one_line=False, show_n=True)
        if equal:
            lo = min(p.iloc[:, 0].min(), p.iloc[:, 1].min())
            hi = max(p.iloc[:, 0].max(), p.iloc[:, 1].max())
            m = 0.05 * (hi - lo)
            ax.set_xlim(lo - m, hi + m)
            ax.set_ylim(lo - m, hi + m)
        ax.set_xlabel(axis_label(xv))
        ax.set_ylabel(axis_label(yv))
        ax.set_title(f'({pf.panel_letters[k]})', loc='left')
    sm_ = mpl.cm.ScalarMappable(norm=norm, cmap=pf.DD_CMAP)
    if len(PANELS) < n_rows * N_COLS:                   # an empty grid position: colour bar goes there
        k = len(PANELS)
        holder = fig.add_subplot(gs[k // N_COLS, k % N_COLS])
        holder.set_axis_off()
        cax = holder.inset_axes([(1 - CBAR_WIDTH) / 2, 0.55, CBAR_WIDTH, 0.06])
        cbar = fig.colorbar(sm_, cax=cax, orientation='horizontal')
        label = CBAR_LABEL.replace(' to middle', '\nto middle')
    else:                                               # grid full: colour bar below the panels
        cbar = fig.colorbar(sm_, ax=axes, location='bottom', orientation='horizontal',
                            shrink=CBAR_WIDTH, aspect=40)
        label = CBAR_LABEL
    cbar.set_label(label, fontsize=pf.FONT_SIZE_NORMAL)
    cbar.ax.tick_params(labelsize=pf.FONT_SIZE_SMALL)
    cbar.outline.set_linewidth(pf.LW_THIN)
    return fig


# ══════════════════════════ REGRESSION ASSUMPTIONS ══════════════════════════
def fit_ols(data, xv, yv):
    """OLS of y on x, rows ordered by SITE, YEAR, then shading timing (the order Durbin–Watson uses),
    so neighbouring residuals are consecutive shading dates of the same season."""
    q = data[['SITE', pf.YEAR_COL, pf.X_COL, pf.pct_col(xv), pf.pct_col(yv)]].dropna()
    q = q.sort_values(['SITE', pf.YEAR_COL, pf.X_COL])
    X = sm.add_constant(q[pf.pct_col(xv)].to_numpy(dtype=float))
    return sm.OLS(q[pf.pct_col(yv)].to_numpy(dtype=float), X).fit(), X, q


def regression_assumptions(data, xv, yv, site):
    """One row of assumption tests for the regression of yv on xv in `data`."""
    row = {'SITE': site, 'x': xv, 'y': yv}
    res, X, q = fit_ols(data, xv, yv)
    n = len(q)
    row['n'] = n
    if n < MIN_N_ASSUMPTIONS or q[pf.pct_col(xv)].nunique() < 3:
        row['note'] = f'not tested (n = {n})'
        return row
    resid = res.resid

    # 1. Normality of residuals
    if n <= 5000:
        row['normality_test'], row['normality_p'] = 'Shapiro-Wilk', stats.shapiro(resid).pvalue
    else:
        row['normality_test'], row['normality_p'] = "D'Agostino K2", stats.normaltest(resid).pvalue
    row['resid_skew'] = stats.skew(resid)
    row['resid_excess_kurtosis'] = stats.kurtosis(resid)

    # 2. Constant variance (homoscedasticity)
    row['breusch_pagan_p'] = het_breuschpagan(resid, X)[1]

    # 3. Linearity: does adding fitted^2 improve the model?
    row['reset_p'] = float(linear_reset(res, power=2, use_f=True).pvalue)

    # 4. Independence of residuals (ordered by year, then shading timing)
    row['durbin_watson'] = durbin_watson(resid)

    # 5. Influential points
    cooks = res.get_influence().cooks_distance[0]
    row['n_cooks_gt_4_over_n'] = int((cooks > 4 / n).sum())
    row['max_cooks_distance'] = float(cooks.max())

    # Pass / fail
    row['normal_ok'] = row['normality_p'] >= ASSUMPTION_ALPHA
    row['equal_variance_ok'] = row['breusch_pagan_p'] >= ASSUMPTION_ALPHA
    row['linear_ok'] = row['reset_p'] >= ASSUMPTION_ALPHA
    row['independent_ok'] = DW_OK[0] <= row['durbin_watson'] <= DW_OK[1]
    row['all_ok'] = all(row[k] for k in ['normal_ok', 'equal_variance_ok', 'linear_ok', 'independent_ok'])
    return row


def assumption_table(d):
    t = pd.DataFrame([regression_assumptions(d, xv, yv, 'all') for xv, yv, _ in PANELS])
    t['relationship'] = [short_name(x, y) for x, y in zip(t['x'], t['y'])]
    return t


def print_assumptions(t):
    flags = ['normal_ok', 'equal_variance_ok', 'linear_ok', 'independent_ok']
    show = t[['SITE', 'relationship', 'n', 'normality_p', 'breusch_pagan_p', 'reset_p', 'durbin_watson',
              'n_cooks_gt_4_over_n'] + flags].copy()
    for c in flags:
        show[c] = show[c].map({True: 'yes', False: 'NO'})
    with pd.option_context('display.width', 250, 'display.max_columns', 30, 'display.float_format', '{:.3g}'.format):
        print('\nLinear-regression assumption checks (p < '
              f'{ASSUMPTION_ALPHA:g} = assumption rejected; Durbin–Watson outside {DW_OK} = autocorrelated)')
        print(show.to_string(index=False))
    print('\nPanels meeting each assumption:')
    for c in flags:
        print(f'  {c:18s} {int(t[c].fillna(False).astype(bool).sum())} of {t[c].notna().sum()}')


def figure_diagnostics(data, norm, title):
    """Residuals vs fitted, normal Q-Q and scale-location for each relationship (one row each)."""
    fig, axes = plt.subplots(len(PANELS), 3, figsize=pf.fig_size('double', height_mm=60 * len(PANELS)),
                             layout='constrained')
    axes = np.atleast_2d(axes)
    for i, (xv, yv, _) in enumerate(PANELS):
        res, _, q = fit_ols(data, xv, yv)
        if len(q) < MIN_N_ASSUMPTIONS:
            for ax in axes[i]:
                ax.text(0.5, 0.5, f'n = {len(q)}', transform=ax.transAxes, ha='center')
            continue
        fitted, resid = res.fittedvalues, res.resid
        std_resid = res.get_influence().resid_studentized_internal
        colour = dict(c=q[pf.X_COL], cmap=pf.DD_CMAP, norm=norm, s=3, linewidths=0, rasterized=True)
        name = f'{pf.var_style(yv)["short"]} ~ {pf.var_style(xv)["short"]}'

        ax = axes[i, 0]                               # residuals vs fitted: linearity, equal variance
        ax.scatter(fitted, resid, **colour)
        ax.axhline(0, color='black', linestyle='--', linewidth=pf.LW_THIN)
        ax.set_xlabel('Fitted value (%)')
        ax.set_ylabel('Residual (%)')
        ax.set_title(f'{name}: residuals vs fitted', loc='left', fontsize=pf.FONT_SIZE_SMALL)

        ax = axes[i, 1]                               # normal Q-Q: normality
        (osm, osr), (slope, intercept, _) = stats.probplot(std_resid, dist='norm')
        ax.scatter(osm, osr, s=3, color='#4D4D4D', linewidths=0, rasterized=True)
        ax.plot(osm, slope * osm + intercept, color='black', linestyle='--', linewidth=pf.LW_THIN)
        ax.set_xlabel('Theoretical quantile')
        ax.set_ylabel('Standardised residual')
        ax.set_title(f'{name}: normal Q-Q', loc='left', fontsize=pf.FONT_SIZE_SMALL)

        ax = axes[i, 2]                               # scale-location: equal variance
        ax.scatter(fitted, np.sqrt(np.abs(std_resid)), **colour)
        ax.set_xlabel('Fitted value (%)')
        ax.set_ylabel('√|standardised residual|')
        ax.set_title(f'{name}: scale-location', loc='left', fontsize=pf.FONT_SIZE_SMALL)
    cbar = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=pf.DD_CMAP), ax=axes, orientation='horizontal',
                        location='bottom', shrink=0.45, aspect=40)
    cbar.set_label(CBAR_LABEL, fontsize=pf.FONT_SIZE_NORMAL)
    cbar.ax.tick_params(labelsize=pf.FONT_SIZE_SMALL)
    fig.suptitle(title, fontsize=pf.FONT_SIZE_TITLE)
    return fig


def main():
    start = pf.start_script(__file__)
    d = prepare()
    norm = mpl.colors.Normalize(vmin=d[pf.X_COL].min(), vmax=d[pf.X_COL].max())

    print('\nRelationship statistics (Theil–Sen, Kendall, cluster-robust OLS), all sites pooled')
    table = relationship_table(d)
    print_relationships(table)
    pf.save_table(table, f'{FILE_BASE}_relationships')
    pf.save(make_figure(d, norm, table), FILE_BASE)

    # Linear-regression assumptions
    assumptions = assumption_table(d)
    print_assumptions(assumptions)
    pf.save_table(assumptions, f'{FILE_BASE}_regression_assumptions')
    pf.save(figure_diagnostics(d, norm, 'All sites pooled: regression diagnostics'),
            f'{FILE_BASE}_regression_diagnostics')
    pf.finish_script(start)


if __name__ == '__main__':
    main()