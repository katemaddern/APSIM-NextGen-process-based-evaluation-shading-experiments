"""
Methods 2.2, Table 1: climate summary for each study site (1995-2024).

Reads the APSIM .met files (with Cape Grim CO2) for each site and writes
'table_1_methods_climate_information_for_sites.csv' to cfg.SECOND_DRAFT_DIR,
with weather variables as rows and sites as columns. Each cell is
"mean ± standard deviation".

  - Annual / growing-season rainfall: mean ± SD of yearly totals.
    Growing season = April to October.
  - Radiation, max/min temperature, evaporation: mean ± SD of daily values
    across all days of the year, 1995-2024.
"""

import glob
import os
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Locate config_loader.py and paper_1_functions.py
# --------------------------------------------------------------------------
try:
    SCRIPTS_BASE = Path(__file__).resolve().parents[1]
except NameError:
    SCRIPTS_BASE = Path("$HOME/APSIM-NextGen-process-based-evaluation-shading-experiments")

if str(SCRIPTS_BASE) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg            # noqa: E402
import paper_1_functions as pf           # noqa: E402

START_YEAR = 1995
END_YEAR = 2024
GROWING_SEASON_MONTHS = [4, 5, 6, 7, 8, 9, 10]
OUTPUT_FILE = "table_1_methods_section_221_climate_information_for_sites.csv"

# Order of rows in the output table: (column in data, how to summarise, label)
VARIABLES = [
    ("RAIN", "annual_total",         "Mean annual rainfall (mm)"),
    ("RAIN", "growing_season_total", "Mean growing season rainfall (mm)"),
    ("RADN", "daily",                "Mean daily radiation (MJ m⁻² day⁻¹)"),
    ("MAXT", "daily",                "Mean daily maximum temperature (°C)"),
    ("MINT", "daily",                "Mean daily minimum temperature (°C)"),
    ("EVAP", "daily",                "Mean daily evaporation (mm)"),
]


def read_met_file(path):
    """Read one APSIM .met file into a DataFrame."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()

    # Header is the first line starting with 'year'; units line follows
    header_idx = next(i for i, l in enumerate(lines)
                      if l.strip().startswith("year"))
    columns = lines[header_idx].split()
    rows = [l.split() for l in lines[header_idx + 2:] if l.strip()]

    df = pd.DataFrame(rows, columns=columns)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    fname = os.path.basename(path)
    df.insert(0, "FILE", fname)
    df.insert(1, "SITE", fname.split("_", 1)[0])
    print(f"{fname}: {len(df)} rows")
    return df


def load_climate_data(folder):
    paths = sorted(glob.glob(os.path.join(folder, "*.sim")))
    if not paths:
        raise FileNotFoundError(f"No .met files found in {folder}")

    df = pd.concat([read_met_file(p) for p in paths],
                   ignore_index=True, sort=False)

    df.columns = df.columns.str.upper().str.replace(".", "_", regex=False)
    df = df.rename(columns={"DAY": "DOY"})
    df["DATE"] = pd.to_datetime(
        df["YEAR"].astype(str) + df["DOY"].astype(str).str.zfill(3),
        format="%Y%j",
    )
    df["MONTH"] = df["DATE"].dt.month

    return df[(df["YEAR"] >= START_YEAR) & (df["YEAR"] <= END_YEAR)]


def summarise(df, column, method):
    """Return a DataFrame indexed by SITE with 'mean' and 'std' columns."""
    if method == "annual_total":
        values = df.groupby(["SITE", "YEAR"])[column].sum()
    elif method == "growing_season_total":
        gs = df[df["MONTH"].isin(GROWING_SEASON_MONTHS)]
        values = gs.groupby(["SITE", "YEAR"])[column].sum()
    elif method == "daily":
        values = df.set_index("SITE")[column]
    else:
        raise ValueError(f"Unknown method: {method}")

    return values.groupby(level="SITE").agg(["mean", "std"])


def build_table(df):
    rows = {}
    for column, method, label in VARIABLES:
        s = summarise(df, column, method)
        rows[label] = (s["mean"].map("{:.1f}".format) + " ± "
                       + s["std"].map("{:.1f}".format))

    table = pd.DataFrame(rows).T          # variables as rows, sites as columns
    table = table[pf.site_order]           # order sites
    table.columns = pf.format_site_names(pd.Series(table.columns).astype(str))
    table.index.name = ""
    table.columns.name = None
    return table


def main():
    df = load_climate_data(cfg.EXAMPLE_DATA_FILES_DIR)
    print(f"Years: {df['YEAR'].min()}-{df['YEAR'].max()}")

    table = build_table(df)
    print(table.to_string())

    out_path = Path(cfg.SECOND_DRAFT_DIR) / OUTPUT_FILE
    # utf-8-sig so Excel displays ±, ° and superscripts correctly
    table.to_csv(out_path, encoding="utf-8-sig")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()