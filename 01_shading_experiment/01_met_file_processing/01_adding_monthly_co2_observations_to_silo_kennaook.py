"""
append_co2_batch.py

Appends monthly Cape Grim (Tasmania) baseline CO2 observations, as provided
in the default CSIRO download (CapeGrim_CO2_data_download.csv), as a new
'co2' column onto one or more SILO/APSIM .sim/.met weather files, while
leaving all existing station metadata, column formatting, and CRLF line
endings untouched.

CAPE GRIM FILE LAYOUT (default CSIRO download)
----------------------------------------------
    YYYY,MM,DD,DATE,CO2(ppm),SD(ppm),GR(ppm/yr),Source
    1976,5,15,1976.3689,328.861,0.165,NaN,in situ
    ...
    <blank rows>
    Terms of Use,,,,,,,
    <several dozen lines of licence text>

  - One row per month (DD is always 15, i.e. a monthly value stamped
    mid-month). Only YYYY, MM and CO2(ppm) are used.
  - 'Source' is 'in situ' or 'flask'. Both are kept by default
    (the CSIRO record is a merged series); use --source to restrict.
  - The file ends in a free-text Terms of Use block and is Latin-1
    (not UTF-8) encoded, so non-data rows are discarded by requiring a
    numeric year, month and CO2 value.
  - The record starts in May 1976 and ends at the most recent processed
    month (typically a month or two before the download date).

USAGE (command line)
---------------------
Single file:
    python append_co2_batch.py --co2 CapeGrim_CO2_data_download.csv \
        --input lameroo_25509.sim --outdir final_met_files

Many files (folder of .sim files), matched by glob:
    python append_co2_batch.py --co2 CapeGrim_CO2_data_download.csv \
        --input-dir raw_data --pattern "paper_2_*.sim" --outdir final_met_files

With explicit fill values instead of holding the first/last observation:
    python append_co2_batch.py --co2 CapeGrim_CO2_data_download.csv \
        --input lameroo_25509.sim --outdir final_met_files \
        --fill-before 328 --fill-after 425

USAGE (as a library, inside your own workflow script)
-------------------------------------------------------
    from append_co2_batch import append_co2_to_met

    append_co2_to_met(
        met_path="raw_data/lameroo_25509.sim",
        co2_path="raw_data/CapeGrim_CO2_data_download.csv",
        out_path="final_met_files/lameroo_25509.met",
    )

FILL LOGIC
----------
Every (year, month) in the weather file is looked up against the Cape
Grim monthly record. If there's no observation for that month:
    - month is before the first Cape Grim month -> `fill_before`
    - month is after the last Cape Grim month   -> `fill_after`
    - month falls in an internal gap            -> linear interpolation
                                                   between neighbouring
                                                   observed months
If `fill_before` / `fill_after` are None (the default), the first / last
observed Cape Grim value is carried backward / forward. This matters for
SILO files, which usually start before May 1976 (a few months to decades)
and run to the current date, i.e. past the end of the processed record.
"""

import argparse
import datetime
import glob
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

NEW_COL_WIDTH = 6  # chars; fits values like 328.86 / 425.19

YearMonth = Tuple[int, int]


@dataclass
class Co2AppendResult:
    out_path: str
    n_rows: int
    n_observed: int
    n_filled_before: int
    n_filled_after: int
    n_interpolated: int
    fill_before_value: float
    fill_after_value: float
    years_filled_before: Tuple[int, ...]
    years_filled_after: Tuple[int, ...]


@dataclass
class Co2Record:
    lookup: Dict[YearMonth, float]
    first: YearMonth
    last: YearMonth


def _ym_index(ym: YearMonth) -> int:
    """Continuous month counter, for ordering and interpolation."""
    return ym[0] * 12 + (ym[1] - 1)


def _load_co2_record(co2_path: str, source: str = "all") -> Co2Record:
    """
    Read the CSIRO Cape Grim monthly CO2 csv.

    Drops the trailing Terms of Use text (and any other non-data rows) by
    keeping only rows with a numeric year, month and CO2 value.
    `source` may be 'all', 'in situ' or 'flask'.
    """
    df = pd.read_csv(co2_path, encoding="latin-1", dtype=str, skip_blank_lines=True)
    df.columns = df.columns.str.strip()

    df = df.rename(columns={"YYYY": "year", "MM": "month", "CO2(ppm)": "co2", "Source": "source"})
    missing = {"year", "month", "co2"} - set(df.columns)
    if missing:
        raise ValueError(
            f"{co2_path}: expected Cape Grim columns YYYY, MM, CO2(ppm); "
            f"missing {sorted(missing)}. Found: {list(df.columns)}"
        )

    for col in ("year", "month", "co2"):
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")
    df = df.dropna(subset=["year", "month", "co2"])

    if "source" in df.columns:
        df["source"] = df["source"].str.strip().str.lower()
        if source != "all":
            df = df[df["source"] == source.lower()]
    elif source != "all":
        raise ValueError(f"{co2_path}: no 'Source' column, cannot filter to {source!r}")

    if df.empty:
        raise ValueError(f"{co2_path}: no usable CO2 rows found (source={source!r})")

    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)

    # Guard against duplicate months (not expected in the default download,
    # but possible if files are merged); average them rather than silently
    # keeping whichever came last.
    df = df.groupby(["year", "month"], as_index=False)["co2"].mean()

    lookup = {(int(r.year), int(r.month)): float(r.co2) for r in df.itertuples()}
    keys = sorted(lookup, key=_ym_index)
    return Co2Record(lookup=lookup, first=keys[0], last=keys[-1])


def _interpolate_gap(record: Co2Record, ym: YearMonth) -> float:
    """Linear interpolation for a month inside the record with no value."""
    target = _ym_index(ym)
    idx = {_ym_index(k): v for k, v in record.lookup.items()}
    lo = max(i for i in idx if i < target)
    hi = min(i for i in idx if i > target)
    frac = (target - lo) / (hi - lo)
    return idx[lo] + frac * (idx[hi] - idx[lo])


def append_co2_to_met(
    met_path: str,
    co2_path: str,
    out_path: str,
    fill_before: Optional[float] = None,  # None -> first Cape Grim value (May 1976)
    fill_after: Optional[float] = None,   # None -> latest Cape Grim value
    source: str = "all",
    co2_record: Optional[Co2Record] = None,
) -> Co2AppendResult:
    """
    Append a 'co2' column to a single SILO/APSIM .sim/.met file.

    Parameters
    ----------
    met_path : path to the source .sim/.met file
    co2_path : path to CapeGrim_CO2_data_download.csv
        (ignored if co2_record is supplied)
    out_path : where to write the new .met file
    fill_before : value for months before the start of the Cape Grim
        record; None carries the first observed value backward
    fill_after : value for months after the end of the Cape Grim record;
        None carries the last observed value forward
    source : 'all' (default), 'in situ' or 'flask'
    co2_record : optional pre-loaded record from _load_co2_record(), so
        the CSV is read once and reused across many files in a batch

    Returns
    -------
    Co2AppendResult with basic stats about what was observed/filled.
    """
    if co2_record is None:
        co2_record = _load_co2_record(co2_path, source=source)

    before_val = co2_record.lookup[co2_record.first] if fill_before is None else float(fill_before)
    after_val = co2_record.lookup[co2_record.last] if fill_after is None else float(fill_after)
    first_i, last_i = _ym_index(co2_record.first), _ym_index(co2_record.last)

    with open(met_path, "rb") as f:
        raw = f.read()

    lines = raw.split(b"\r\n")
    trailing_blank = bool(lines) and lines[-1] == b""
    if trailing_blank:
        lines = lines[:-1]
    lines = [l.decode("utf-8") for l in lines]

    header_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("year"))
    units_idx = header_idx + 1
    data_start_idx = units_idx + 1

    header_line = lines[header_idx]
    if "co2" in header_line.split():
        raise ValueError(f"{met_path} already has a 'co2' column")
    units_line = lines[units_idx]
    data_lines = lines[data_start_idx:]

    new_header_line = header_line + "  " + "co2".rjust(NEW_COL_WIDTH)
    new_units_line = units_line + "  " + "(ppm)".rjust(NEW_COL_WIDTH)

    new_data_lines = []
    years_filled_before, years_filled_after = set(), set()
    n_obs = n_before = n_after = n_interp = 0
    interp_cache: Dict[YearMonth, float] = {}

    for line in data_lines:
        if not line.strip():
            new_data_lines.append(line)
            continue
        tokens = line.split()
        year = int(tokens[0])
        day = int(tokens[1])
        month = datetime.datetime.strptime(f"{year}{day:03d}", "%Y%j").month
        ym = (year, month)

        co2_val = co2_record.lookup.get(ym)
        if co2_val is not None:
            n_obs += 1
        elif _ym_index(ym) < first_i:
            co2_val = before_val
            years_filled_before.add(year)
            n_before += 1
        elif _ym_index(ym) > last_i:
            co2_val = after_val
            years_filled_after.add(year)
            n_after += 1
        else:
            if ym not in interp_cache:
                interp_cache[ym] = _interpolate_gap(co2_record, ym)
            co2_val = interp_cache[ym]
            n_interp += 1

        new_data_lines.append(line + "  " + f"{co2_val:.2f}".rjust(NEW_COL_WIDTH))

    out_lines = lines[:header_idx] + [new_header_line, new_units_line] + new_data_lines
    out_text = "\r\n".join(out_lines)
    if trailing_blank:
        out_text += "\r\n"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(out_text.encode("utf-8"))

    return Co2AppendResult(
        out_path=out_path,
        n_rows=len(new_data_lines),
        n_observed=n_obs,
        n_filled_before=n_before,
        n_filled_after=n_after,
        n_interpolated=n_interp,
        fill_before_value=before_val,
        fill_after_value=after_val,
        years_filled_before=tuple(sorted(years_filled_before)),
        years_filled_after=tuple(sorted(years_filled_after)),
    )


def batch_append_co2(
    input_paths,
    co2_path: str,
    outdir: str,
    fill_before: Optional[float] = None,
    fill_after: Optional[float] = None,
    source: str = "all",
    out_ext: str = "_with_cape_grim_co2.met",
):
    """
    Run append_co2_to_met() over many files, reusing a single Cape Grim
    record for speed. Output filenames are the input stem + `out_ext`.
    """
    record = _load_co2_record(co2_path, source=source)
    print(
        f"Cape Grim record ({source}): {record.first[0]}-{record.first[1]:02d} "
        f"to {record.last[0]}-{record.last[1]:02d}, {len(record.lookup)} months"
    )
    results = []
    for met_path in input_paths:
        stem = os.path.splitext(os.path.basename(met_path))[0]
        out_path = os.path.join(outdir, stem + out_ext)
        result = append_co2_to_met(
            met_path=met_path,
            co2_path=co2_path,
            out_path=out_path,
            fill_before=fill_before,
            fill_after=fill_after,
            source=source,
            co2_record=record,
        )
        results.append(result)
        print(
            f"[ok] {met_path} -> {result.out_path} "
            f"({result.n_rows} rows; {result.n_observed} observed; "
            f"{result.n_filled_before} filled before record @ {result.fill_before_value:.2f}; "
            f"{result.n_filled_after} filled after record @ {result.fill_after_value:.2f}; "
            f"{result.n_interpolated} interpolated)"
        )
    return results


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--co2", required=True, help="Path to CapeGrim_CO2_data_download.csv")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="Path to a single .sim/.met file")
    src.add_argument("--input-dir", help="Folder containing many .sim/.met files")
    p.add_argument("--pattern", default="*.sim", help="Glob pattern used with --input-dir (default: *.sim)")
    p.add_argument("--outdir", required=True, help="Folder to write the output .met files into")
    p.add_argument("--out-ext", default="_with_cape_grim_co2.met",
                   help="Suffix + extension for output files (default: _with_cape_grim_co2.met)")
    p.add_argument("--fill-before", type=float, default=None,
                   help="CO2 (ppm) for months before the Cape Grim record starts "
                        "(default: first observed value)")
    p.add_argument("--fill-after", type=float, default=None,
                   help="CO2 (ppm) for months after the Cape Grim record ends "
                        "(default: latest observed value)")
    p.add_argument("--source", choices=["all", "in situ", "flask"], default="all",
                   help="Which Cape Grim sampling source to use (default: all)")
    return p.parse_args()


def main():
    args = _parse_args()
    if args.input:
        input_paths = [args.input]
    else:
        input_paths = sorted(glob.glob(os.path.join(args.input_dir, args.pattern)))
        if not input_paths:
            raise SystemExit(f"No files matched {args.pattern!r} in {args.input_dir!r}")

    batch_append_co2(
        input_paths=input_paths,
        co2_path=args.co2,
        outdir=args.outdir,
        fill_before=args.fill_before,
        fill_after=args.fill_after,
        source=args.source,
        out_ext=args.out_ext,
    )


if __name__ == "__main__":
    main()