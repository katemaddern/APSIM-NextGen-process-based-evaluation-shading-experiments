import json
import glob
import math
import csv
import os
import sys
from pathlib import Path

# ================================================================
# CONFIGURATION
# ================================================================

# ---- Load shared path configuration ----
# SCRIPTS_BASE is two levels up from this file
# (paper_2/02_simulation_set_up/this_script.py -> paper_2/)
# Needed so the cfg object can be imported from config_loader.py.
#
# Optional: pass a folder on the command line to audit a different
# folder without touching config.sh, e.g.
#     python this_script.py /path/to/apsimx/folder

if len(sys.argv) > 1:
    FOLDER = sys.argv[1]
else:
    SCRIPTS_BASE = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(SCRIPTS_BASE))
    from config_loader import cfg
    FOLDER = cfg.DRYLAND_APSIM_TEMPLATES_BEFORE_CHECKING_DIR

OUTPUT_CSV = os.path.join(
    FOLDER,
    "apsim_initial_conditions_audit.csv"
)

# ---------------------------------------------------------------
# Soil water: 30 mm of PAW, filled from the top
# ---------------------------------------------------------------

PAW_MM_TARGET = 30.0          # mm, summed over the profile
PAW_MM_TOLERANCE = 0.1        # mm
LAYER_TOLERANCE = 1e-6        # mm/mm, used for the filled-from-top shape

# ---------------------------------------------------------------
# Soil mineral N (totals summed over layers, must be in kg/ha)
# ---------------------------------------------------------------

CHECK_N = True
NO3_TARGET = 40.0             # kg/ha, summed over layers
NH4_TARGET = 5.0              # kg/ha, summed over layers
N_TOLERANCE = 0.01            # kg/ha

# APSIM Solute.InitialValuesUnits: 0 = ppm, 1 = kg/ha.
KGHA_UNITS_CODE = 1

# ---------------------------------------------------------------
# Management targets
# ---------------------------------------------------------------

SOWING_MANAGER_NAME = "Sow on a fixed date"
SOW_DATE_TARGET = "7-may"     # compared case-insensitively

# Must NOT be present in the dryland files
RESET_MANAGER_NAME = "Reset on date"

# Must be present (name matched case-insensitively, so "Nbank" and
# "NBank" both count); its Threshold is printed
NBANK_MANAGER_NAME = "NBank"

# Must be present, with Crop set to Wheat
IRRIGATE_MANAGER_NAME = "Irrigate at sowing"
IRRIGATE_CROP_TARGET = "Wheat"   # "[Wheat]" in the file is accepted

# ---------------------------------------------------------------
# Clock and report
# ---------------------------------------------------------------

CHECK_CLOCK = True
CLOCK_START_TARGET = "2024-01-01T00:00:00"
CLOCK_END_TARGET = "2025-02-28T00:00:00"

REPORT_EVENT_TARGET = ["[Clock].EndOfDay"]
REPORT_REQUIRED_VARIABLES = [
    "[Clock].Today",
    "[Wheat].Leaf.Photosynthesis.FCO2",
]


# ================================================================
# GENERAL HELPERS
# ================================================================

def close_to(value, target, tolerance):
    try:
        return math.isclose(
            float(value), float(target),
            abs_tol=tolerance, rel_tol=0.0
        )
    except (TypeError, ValueError):
        return False


def status(ok):
    return "OK" if ok else "CHECK"


def parameter_dict(node):
    """Convert an APSIM Manager 'Parameters' array into a dict."""
    params = {}
    if not isinstance(node, dict):
        return params
    for item in node.get("Parameters", []) or []:
        if isinstance(item, dict) and item.get("Key") is not None:
            params[item["Key"]] = item.get("Value")
    return params


def find_children_by_name(node, name):
    """Return direct Children with a particular Name."""
    if not isinstance(node, dict):
        return []
    children = node.get("Children", [])
    if not isinstance(children, list):
        return []
    return [
        c for c in children
        if isinstance(c, dict) and c.get("Name") == name
    ]


def find_all_nodes_by_name(node, name, ignore_case=False):
    """Recursively find every node with the requested Name."""
    matches = []
    if isinstance(node, dict):
        node_name = node.get("Name")
        if isinstance(node_name, str) and (
            node_name.lower() == name.lower() if ignore_case
            else node_name == name
        ):
            matches.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                matches.extend(
                    find_all_nodes_by_name(value, name, ignore_case)
                )
    elif isinstance(node, list):
        for item in node:
            matches.extend(find_all_nodes_by_name(item, name, ignore_case))
    return matches


def find_soils(node):
    """Recursively find all Soil nodes (by $type, falling back to Name)."""
    soils = []
    if isinstance(node, dict):
        node_type = str(node.get("$type", ""))
        if node_type.startswith("Models.Soils.Soil,") or (
            not node_type and node.get("Name") == "Soil"
        ):
            soils.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                soils.extend(find_soils(value))
    elif isinstance(node, list):
        for item in node:
            soils.extend(find_soils(item))
    return soils


# ================================================================
# SOIL CHECK
# ================================================================

def check_solute(soil, solute_name, target, prefix):
    """Sum a Solute node's InitialValues (kg/ha)."""
    result = {
        f"{prefix}_kg_ha": None,
        f"{prefix}_units": None,
        f"{prefix}_status": "ERROR",
    }

    nodes = find_children_by_name(soil, solute_name)
    if not nodes:
        return result

    node = nodes[0]
    values = node.get("InitialValues")
    units = node.get("InitialValuesUnits")
    result[f"{prefix}_units"] = (
        "kg/ha" if units == KGHA_UNITS_CODE
        else "ppm" if units == 0
        else units
    )

    if isinstance(values, list):
        total = sum(float(x) for x in values)
        result[f"{prefix}_kg_ha"] = total
        result[f"{prefix}_status"] = status(
            units == KGHA_UNITS_CODE
            and close_to(total, target, N_TOLERANCE)
        )

    return result


def filled_from_top_shape(sw, ll15, dul):
    """
    True if the profile looks filled from the top: zero or more layers
    at DUL, then at most one partly filled layer, then the rest at LL15.
    """
    state = "full"   # full -> (partial) -> empty
    for s, lo, hi in zip(sw, ll15, dul):
        s, lo, hi = float(s), float(lo), float(hi)
        at_dul = abs(s - hi) <= LAYER_TOLERANCE
        at_ll = abs(s - lo) <= LAYER_TOLERANCE

        if state == "full":
            if at_dul:
                continue
            state = "empty" if at_ll else "partial"
            if state == "partial" and not (lo < s < hi):
                return False
        else:
            if not at_ll:
                return False
    return True


def check_soil(soil):

    result = {
        "PAW_mm": None,
        "PAW_capacity_mm": None,
        "PAW_percent_full": None,
        "PAW_status": "ERROR",
        "FilledFromTop": None,
        "FilledFromTop_shape_ok": None,
        "FilledFromTop_status": "ERROR",
    }

    physical_nodes = find_children_by_name(soil, "Physical")
    water_nodes = find_children_by_name(soil, "Water")

    # ------------------------------------------------------------
    # PAW (mm) = sum((SW - LL15) * thickness), target 30 mm
    # FilledFromTop must be true AND the layer values must actually
    # look filled from the top.
    # ------------------------------------------------------------

    if physical_nodes and water_nodes:

        physical = physical_nodes[0]
        water = water_nodes[0]

        ll15 = physical.get("LL15")
        dul = physical.get("DUL")
        sw = water.get("InitialValues")
        thickness = water.get("Thickness") or physical.get("Thickness")

        result["FilledFromTop"] = water.get("FilledFromTop")

        if all(isinstance(x, list) for x in (ll15, dul, sw, thickness)) \
                and len(ll15) == len(dul) == len(sw) == len(thickness):

            paw = sum(
                (float(sw[i]) - float(ll15[i])) * float(thickness[i])
                for i in range(len(ll15))
            )
            capacity = sum(
                (float(dul[i]) - float(ll15[i])) * float(thickness[i])
                for i in range(len(ll15))
            )

            result["PAW_mm"] = paw
            result["PAW_capacity_mm"] = capacity
            if capacity > 0:
                result["PAW_percent_full"] = 100.0 * paw / capacity

            result["PAW_status"] = status(
                close_to(paw, PAW_MM_TARGET, PAW_MM_TOLERANCE)
            )

            shape_ok = filled_from_top_shape(sw, ll15, dul)
            result["FilledFromTop_shape_ok"] = shape_ok
            result["FilledFromTop_status"] = status(
                result["FilledFromTop"] is True and shape_ok
            )

    # ------------------------------------------------------------
    # NO3 / NH4 totals (reported; only in OVERALL if CHECK_N)
    # ------------------------------------------------------------

    result.update(check_solute(soil, "NO3", NO3_TARGET, "NO3"))
    result.update(check_solute(soil, "NH4", NH4_TARGET, "NH4"))

    return result


# ================================================================
# SOIL LOCATION CHECK
#
# The first word of the file name (text before the first "_",
# e.g. "birchip" in birchip_2024_control_..._SpringVQQ.apsimx)
# must appear somewhere in the Soil node's descriptive text fields
# (Site, NearestTown, Region, DataSource, Comments, ...).
# Case-insensitive.
# ================================================================

def check_soil_location(soil, filename):

    site_word = Path(filename).stem.split("_")[0].strip()

    matched_fields = []
    if site_word:
        for key, value in soil.items():
            if key in ("Children", "$type"):
                continue
            if isinstance(value, str) and site_word.lower() in value.lower():
                matched_fields.append(key)

    return {
        "Site_word_from_filename": site_word,
        "Site_found_in_soil_fields": " | ".join(matched_fields),
        "Soil_NearestTown": soil.get("NearestTown"),
        "Site_status": status(bool(matched_fields)),
    }


# ================================================================
# MANAGEMENT CHECKS
# ================================================================

def strip_brackets(value):
    """'[Wheat]' -> 'Wheat'."""
    if not isinstance(value, str):
        return value
    return value.strip().strip("[]").strip()


def check_management(data):

    result = {}

    # ---------------- Sowing date ----------------
    nodes = find_all_nodes_by_name(data, SOWING_MANAGER_NAME)

    if nodes:
        sow_date = parameter_dict(nodes[0]).get("SowDate")
        result["SowDate"] = sow_date
        result["SowDate_status"] = status(
            isinstance(sow_date, str)
            and sow_date.strip().lower() == SOW_DATE_TARGET.lower()
        )
    else:
        result["SowDate"] = None
        result["SowDate_status"] = "ERROR"

    # ---------------- Reset on date: must be ABSENT ----------------
    nodes = find_all_nodes_by_name(data, RESET_MANAGER_NAME)
    result["Reset_present"] = bool(nodes)
    result["Reset_Enabled"] = nodes[0].get("Enabled") if nodes else None
    result["Reset_absent_status"] = status(not nodes)

    # ---------------- NBank: must be PRESENT ----------------
    nodes = find_all_nodes_by_name(data, NBANK_MANAGER_NAME, ignore_case=True)
    result["NBank_present"] = bool(nodes)

    if nodes:
        node = nodes[0]
        params = parameter_dict(node)
        result["NBank_name"] = node.get("Name")
        result["NBank_Enabled"] = node.get("Enabled", True)
        result["NBank_Threshold_kg_ha"] = params.get("Threshold")
        result["NBank_FertiliserType"] = params.get("FertiliserType")
        result["NBank_status"] = status(node.get("Enabled", True) is True)
    else:
        result["NBank_name"] = None
        result["NBank_Enabled"] = None
        result["NBank_Threshold_kg_ha"] = None
        result["NBank_FertiliserType"] = None
        result["NBank_status"] = "ERROR"

    # ---------------- Irrigate at sowing: present, Crop = Wheat ----------------
    nodes = find_all_nodes_by_name(data, IRRIGATE_MANAGER_NAME)
    result["Irrigate_present"] = bool(nodes)

    if nodes:
        node = nodes[0]
        params = parameter_dict(node)
        crop = params.get("Crop")
        crop_ok = (
            isinstance(crop, str)
            and strip_brackets(crop).lower() == IRRIGATE_CROP_TARGET.lower()
        )
        result["Irrigate_Enabled"] = node.get("Enabled", True)
        result["Irrigate_Crop"] = crop
        result["Irrigate_Amount_mm"] = params.get("Amount")
        result["Irrigate_status"] = status(
            crop_ok and node.get("Enabled", True) is True
        )
    else:
        result["Irrigate_Enabled"] = None
        result["Irrigate_Crop"] = None
        result["Irrigate_Amount_mm"] = None
        result["Irrigate_status"] = "ERROR"

    return result


# ================================================================
# CLOCK AND REPORT
# ================================================================

def check_clock(data):
    clocks = find_all_nodes_by_name(data, "Clock")
    if not clocks:
        return {
            "Clock_Start": None, "Clock_End": None,
            "Clock_status": "ERROR",
        }
    start = clocks[0].get("Start")
    end = clocks[0].get("End")
    return {
        "Clock_Start": start,
        "Clock_End": end,
        "Clock_status": status(
            start == CLOCK_START_TARGET and end == CLOCK_END_TARGET
        ),
    }


def check_report(data):
    reports = find_all_nodes_by_name(data, "Report")
    if not reports:
        return {
            "Report_EventNames": None,
            "Report_has_FCO2": None,
            "Report_missing_variables": None,
            "Report_status": "ERROR",
        }
    report = reports[0]
    events = report.get("EventNames") or []
    variables = report.get("VariableNames") or []
    missing = [v for v in REPORT_REQUIRED_VARIABLES if v not in variables]
    return {
        "Report_EventNames": " | ".join(events),
        "Report_has_FCO2": "[Wheat].Leaf.Photosynthesis.FCO2" in variables,
        "Report_missing_variables": " | ".join(missing),
        "Report_status": status(events == REPORT_EVENT_TARGET and not missing),
    }


# ================================================================
# OVERALL STATUS
# ================================================================

def calculate_overall(soil_result, management_result,
                      clock_result, report_result):
    """Return (overall_status, list_of_reasons)."""

    s, m, r, c = soil_result, management_result, report_result, clock_result

    # (status, reason shown when status is not OK)
    checks = [
        (s["PAW_status"],
         f"PAW {fmt(s['PAW_mm'])} mm, not {PAW_MM_TARGET:g} mm"),
        (s["FilledFromTop_status"],
         "water not filled from top"
         f" (FilledFromTop={s['FilledFromTop']}, "
         f"profile shape ok={s['FilledFromTop_shape_ok']})"),
        (s["Site_status"],
         f"'{s['Site_word_from_filename']}' not in soil "
         f"(NearestTown={s['Soil_NearestTown']})"),
        (m["SowDate_status"],
         f"SowDate {m['SowDate']}, not {SOW_DATE_TARGET}"),
        (m["Reset_absent_status"],
         "Reset on date present"),
        (m["NBank_status"],
         "NBank missing" if not m["NBank_present"]
         else "NBank disabled"),
        (m["Irrigate_status"],
         "Irrigate at sowing missing" if not m["Irrigate_present"]
         else f"Irrigate at sowing Crop={m['Irrigate_Crop']}, "
              f"Enabled={m['Irrigate_Enabled']}"),
        (r["Report_status"],
         "Report missing" if r["Report_EventNames"] is None
         else "Report "
         + ", ".join(filter(None, [
             f"missing {r['Report_missing_variables']}"
             if r["Report_missing_variables"] else "",
             f"events {r['Report_EventNames']}"
             if r["Report_EventNames"] != " | ".join(REPORT_EVENT_TARGET)
             else "",
         ]))),
    ]
    if CHECK_N:
        checks += [
            (s["NO3_status"],
             f"NO3 {fmt(s['NO3_kg_ha'])} {s['NO3_units']}, "
             f"not {NO3_TARGET:g} kg/ha"),
            (s["NH4_status"],
             f"NH4 {fmt(s['NH4_kg_ha'])} {s['NH4_units']}, "
             f"not {NH4_TARGET:g} kg/ha"),
        ]
    if CHECK_CLOCK:
        checks.append(
            (c["Clock_status"],
             f"Clock {c['Clock_Start']} -> {c['Clock_End']}")
        )

    statuses = [st for st, _ in checks]
    reasons = [reason for st, reason in checks if st != "OK"]

    if any(st == "ERROR" for st in statuses):
        overall = "ERROR"
    elif all(st == "OK" for st in statuses):
        overall = "OK"
    else:
        overall = "CHECK"

    return overall, reasons


def fmt(value, spec=".2f", missing="missing"):
    return format(value, spec) if value is not None else missing


# ================================================================
# RUN AUDIT
# ================================================================

files = sorted(
    glob.glob(os.path.join(FOLDER, "**", "*.apsimx"), recursive=True)
)

print()
print("=" * 120)
print("APSIM DRYLAND INITIAL CONDITIONS AND MANAGEMENT AUDIT")
print("=" * 120)
print(f"Folder: {FOLDER}")
print(f"Found {len(files)} .apsimx files")
print()

if not files:
    print("ERROR: No .apsimx files found.")
    raise SystemExit(1)

csv_rows = []

for filename in files:

    relative_filename = os.path.relpath(filename, FOLDER)

    print("-" * 120)
    print(relative_filename)
    print("-" * 120)

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        management_result = check_management(data)
        clock_result = check_clock(data)
        report_result = check_report(data)

        soils = find_soils(data)

        if not soils:
            print("  ERROR: No Soil nodes found.")
            csv_rows.append({
                "file": relative_filename,
                "soil_number": None,
                "OVERALL": "ERROR",
            })
            continue

        for soil_number, soil in enumerate(soils, start=1):

            soil_result = check_soil(soil)
            soil_result.update(check_soil_location(soil, filename))

            overall, reasons = calculate_overall(
                soil_result, management_result,
                clock_result, report_result
            )

            m = management_result

            # ---------------- Print ----------------
            print(
                f"  Soil {soil_number}: "
                f"PAW={fmt(soil_result['PAW_mm'])} mm "
                f"(target {PAW_MM_TARGET:g}) [{soil_result['PAW_status']}] | "
                f"FilledFromTop={soil_result['FilledFromTop']}, "
                f"profile shape ok={soil_result['FilledFromTop_shape_ok']} "
                f"[{soil_result['FilledFromTop_status']}]"
            )
            if CHECK_N:
                print(
                    f"    Mineral N: "
                    f"NO3={fmt(soil_result['NO3_kg_ha'])} {soil_result['NO3_units']} "
                    f"[{soil_result['NO3_status']}] | "
                    f"NH4={fmt(soil_result['NH4_kg_ha'])} {soil_result['NH4_units']} "
                    f"[{soil_result['NH4_status']}]"
                )
            else:
                print(
                    f"    Mineral N (info only): "
                    f"NO3={fmt(soil_result['NO3_kg_ha'])} {soil_result['NO3_units']} | "
                    f"NH4={fmt(soil_result['NH4_kg_ha'])} {soil_result['NH4_units']}"
                )
            if soil_result["Site_found_in_soil_fields"]:
                print(
                    f"    Soil site: '{soil_result['Site_word_from_filename']}' "
                    f"found in [{soil_result['Site_found_in_soil_fields']}] "
                    f"[{soil_result['Site_status']}]"
                )
            else:
                print(
                    f"    Soil site: '{soil_result['Site_word_from_filename']}' "
                    f"NOT found in soil | NearestTown="
                    f"{soil_result['Soil_NearestTown']} "
                    f"[{soil_result['Site_status']}]"
                )
            print(
                f"    Sowing: SowDate={m['SowDate']} [{m['SowDate_status']}]"
            )
            print(
                f"    Reset on date: "
                + ("present" if m["Reset_present"] else "absent")
                + f" [{m['Reset_absent_status']}]"
            )
            if m["NBank_present"]:
                print(
                    f"    NBank: present ('{m['NBank_name']}', "
                    f"Enabled={m['NBank_Enabled']}) | "
                    f"Threshold={m['NBank_Threshold_kg_ha']} kg/ha "
                    f"[{m['NBank_status']}]"
                )
            else:
                print(f"    NBank: MISSING [{m['NBank_status']}]")
            if m["Irrigate_present"]:
                print(
                    f"    Irrigate at sowing: present | Crop={m['Irrigate_Crop']} "
                    f"| Amount={m['Irrigate_Amount_mm']} mm "
                    f"[{m['Irrigate_status']}]"
                )
            else:
                print(f"    Irrigate at sowing: MISSING [{m['Irrigate_status']}]")
            print(
                f"    Report: FCO2 present={report_result['Report_has_FCO2']} | "
                f"Events={report_result['Report_EventNames']}"
                + (
                    f" | missing: {report_result['Report_missing_variables']}"
                    if report_result["Report_missing_variables"] else ""
                )
                + f" [{report_result['Report_status']}]"
            )
            if CHECK_CLOCK:
                print(
                    f"    Clock: {clock_result['Clock_Start']} -> "
                    f"{clock_result['Clock_End']} "
                    f"[{clock_result['Clock_status']}]"
                )
            if reasons:
                print(f"    OVERALL = {overall}  <-- " + "; ".join(reasons))
            else:
                print(f"    OVERALL = {overall}")

            # ---------------- CSV row ----------------
            row = {"file": relative_filename, "soil_number": soil_number}
            row.update(soil_result)
            row.update(management_result)
            row.update(report_result)
            if CHECK_CLOCK:
                row.update(clock_result)
            row["OVERALL"] = overall
            row["OVERALL_reasons"] = "; ".join(reasons)
            csv_rows.append(row)

    except Exception as e:
        print(f"  ERROR reading file: {e}")
        csv_rows.append({
            "file": relative_filename,
            "soil_number": None,
            "OVERALL": "ERROR",
        })


# ================================================================
# WRITE CSV
# ================================================================

if csv_rows:
    fieldnames = []
    for row in csv_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)


# ================================================================
# FINAL SUMMARY
# ================================================================

print()
print("=" * 120)
print("AUDIT SUMMARY")
print("=" * 120)
print(f"Rows checked: {len(csv_rows)}")
print(f"PASS:  {sum(r.get('OVERALL') == 'OK' for r in csv_rows)}")
print(f"CHECK: {sum(r.get('OVERALL') == 'CHECK' for r in csv_rows)}")
print(f"ERROR: {sum(r.get('OVERALL') == 'ERROR' for r in csv_rows)}")
print()
print("CSV written to:")
print(OUTPUT_CSV)
print()