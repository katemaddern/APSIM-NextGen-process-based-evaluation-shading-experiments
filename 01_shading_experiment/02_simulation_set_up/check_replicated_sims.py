"""
Check the replicated APSIM files for a site. For every expected file it checks:
  a) the file exists
  b) it contains "[Wheat].Leaf.Photosynthesis.FCO2"

Usage:
    python3 check_replicated_sims.py <site>

Writes problem_files_<site>.txt (one line per problem) and exits 0 if all OK, 1 otherwise.
"""
import os
import sys
import time
import datetime
from collections import Counter
from pathlib import Path

REQUIRED_STRING = "[Wheat].Leaf.Photosynthesis.FCO2"

YEAR_RANGE = range(1995, 2025)
SHIFTS = ["shading"]
DOY_RANGE = range(128, 366)
CULTIVARS = ["SpringVQQ", "SpringQ", "SpringQM", "SpringM", "SpringMS", "SpringS",
             "SpringSVS", "SpringVS", "WinterVQ", "WinterQ", "WinterM", "WinterVS"]
VARIABLE = "radiation"
PERCENTCHANGE = "67"

# --- Configuration ------------------------------------------------------------
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))
from config_loader import cfg  # noqa: E402

if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
    print(__doc__)
    sys.exit(2)
site = sys.argv[1]

OUTDIR = cfg.SHADING_APSIM_SIMULATIONS_DIR
REQ = REQUIRED_STRING.encode()


def expected_names():
    return [f"{site}_{year}_{VARIABLE}_{shift}_{PERCENTCHANGE}_{doy:03d}_{cv}.apsimx"
            for year in YEAR_RANGE for shift in SHIFTS
            for doy in DOY_RANGE for cv in CULTIVARS]


def main():
    start = time.time()
    print(f"Check started {datetime.datetime.now()} for site '{site}'")
    print(f"Output dir: {OUTDIR}")
    print(f"Checking: exists, contains '{REQUIRED_STRING}'")

    names = expected_names()
    problems = []   # (status, name, detail)

    for i, name in enumerate(names, 1):
        path = os.path.join(OUTDIR, name)

        # a) exists
        if not os.path.exists(path):
            problems.append(("MISSING", name, ""))
        else:
            # b) contains FCO2
            try:
                with open(path, "rb") as f:
                    if REQ not in f.read():
                        problems.append(("NO_FCO2", name, ""))
            except OSError as e:
                problems.append(("UNREADABLE", name, str(e)))

        if i % 5000 == 0:
            print(f"  checked {i}/{len(names)} ({len(problems)} problems so far)", flush=True)

    # --- Summary -------------------------------------------------------------------
    counts = Counter(s for s, _, _ in problems)
    print(f"\n{site}: {len(names) - len(problems)}/{len(names)} files pass both checks")
    for status in ("MISSING", "UNREADABLE", "NO_FCO2"):
        if counts.get(status):
            print(f"  {status:<11} {counts[status]}")

    # --- Report ----------------------------------------------------------------------
    report = os.path.join(os.getcwd(), f"problem_files_{site}.txt")
    if problems:
        with open(report, "w") as f:
            for status, name, detail in problems:
                f.write(f"{status}\t{name}\t{detail}\n")
        print(f"\nProblem list written to {report}")
    elif os.path.exists(report):
        os.remove(report)

    print(f"\nRESULT: {'ALL OK' if not problems else 'PROBLEMS FOUND'}")
    print(f"Runtime: {time.time() - start:.1f} s")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())