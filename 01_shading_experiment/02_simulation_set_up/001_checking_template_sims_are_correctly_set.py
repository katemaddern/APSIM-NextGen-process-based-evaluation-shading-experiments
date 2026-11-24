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
    FOLDER = cfg.SHADING_APSIM_TEMPLATES_BEFORE_CHECKING_DIR

OUTPUT_CSV = os.path.join(
    FOLDER,
    "apsim_initial_conditions_audit.csv"
)
 
# ---------------------------------------------------------------
# Soil initial-condition targets
# ---------------------------------------------------------------
 
PAW_PERCENT_TARGET = 100.0    # % of plant-available capacity (LL15 -> DUL)
PAW_PERCENT_TOLERANCE = 0.1   # percentage points
LAYER_DUL_TOLERANCE = 1e-6    # mm/mm, each layer must equal DUL
 
NO3_TARGET = 160.0            # kg/ha, summed over layers
NH4_TARGET = 40.0             # kg/ha, summed over layers
N_TOLERANCE = 0.01            # kg/ha
 
# APSIM Solute.InitialValuesUnits: 0 = ppm, 1 = kg/ha.
# The totals above are only meaningful if the values are in kg/ha.
KGHA_UNITS_CODE = 1
 
# ---------------------------------------------------------------
# Management targets
# ---------------------------------------------------------------
 
SOWING_MANAGER_NAME = "Sow on a fixed date"
SOW_DATE_TARGET = "7-may"     # compared case-insensitively
 
RESET_MANAGER_NAME = "Reset on date"
RESET_PARAMETERS = [
    "ResetWater",        # water
    "ResetNutrients",    # soil nutrients
    "ResetSOM",          # surface organic matter
]
 
# ---------------------------------------------------------------
# Secondary checks (kept from the original audit; these pass on
# the example file). Set to False to leave them out of OVERALL.
# ---------------------------------------------------------------
 
CHECK_CLOCK = True
CLOCK_START_TARGET = "2024-01-01T00:00:00"
CLOCK_END_TARGET = "2025-02-28T00:00:00"
 
CHECK_REPORT = True
REPORT_EVENT_TARGET = ["[Clock].EndOfDay"]
REPORT_REQUIRED_VARIABLES = ["[Clock].Today", 
                             "[Wheat].Leaf.Photosynthesis.FCO2",]
 
 
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
 
 
def find_all_nodes_by_name(node, name):
    """Recursively find every node with the requested Name."""
    matches = []
    if isinstance(node, dict):
        if node.get("Name") == name:
            matches.append(node)
        for value in node.values():
            if isinstance(value, (dict, list)):
                matches.extend(find_all_nodes_by_name(value, name))
    elif isinstance(node, list):
        for item in node:
            matches.extend(find_all_nodes_by_name(item, name))
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
 
 
def to_bool(value):
    """APSIM stores manager booleans as strings ('True'/'False')."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False
 
 
# ================================================================
# SOIL CHECK
# ================================================================
 
def check_solute(soil, solute_name, target, prefix):
    """Sum a Solute node's InitialValues and compare to target (kg/ha)."""
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
 
 
def check_soil(soil):
 
    result = {
        "PAW_mm": None,
        "PAW_capacity_mm": None,
        "PAW_percent_full": None,
        "PAW_max_layer_diff_from_DUL": None,
        "PAW_status": "ERROR",
        "FilledFromTop": None,
    }
 
    physical_nodes = find_children_by_name(soil, "Physical")
    water_nodes = find_children_by_name(soil, "Water")
 
    # ------------------------------------------------------------
    # PAW: initial water must be 100% full, i.e. every layer at DUL.
    # PAW (mm) = sum((SW - LL15) * thickness)
    # Capacity = sum((DUL - LL15) * thickness)
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
            max_diff = max(
                abs(float(sw[i]) - float(dul[i]))
                for i in range(len(ll15))
            )
 
            result["PAW_mm"] = paw
            result["PAW_capacity_mm"] = capacity
            result["PAW_max_layer_diff_from_DUL"] = max_diff
 
            if capacity > 0:
                pct = 100.0 * paw / capacity
                result["PAW_percent_full"] = pct
                result["PAW_status"] = status(
                    close_to(pct, PAW_PERCENT_TARGET, PAW_PERCENT_TOLERANCE)
                    and max_diff <= LAYER_DUL_TOLERANCE
                )
 
    # ------------------------------------------------------------
    # NO3 / NH4: Soil -> NO3|NH4 -> InitialValues (kg/ha per layer)
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
        result["Sowing_Enabled"] = nodes[0].get("Enabled", True)
    else:
        result["SowDate"] = None
        result["SowDate_status"] = "ERROR"
        result["Sowing_Enabled"] = None
 
    # ---------------- Reset on date ----------------
    nodes = find_all_nodes_by_name(data, RESET_MANAGER_NAME)
 
    if nodes:
        node = nodes[0]
        params = parameter_dict(node)
        enabled = node.get("Enabled", True) is True
        result["Reset_Enabled"] = enabled
 
        all_on = enabled
        for key in RESET_PARAMETERS:
            value = params.get(key)
            on = to_bool(value)
            result[key] = value
            result[f"{key}_status"] = status(on)
            all_on = all_on and on
 
        result["Reset_status"] = status(all_on)
    else:
        result["Reset_Enabled"] = None
        for key in RESET_PARAMETERS:
            result[key] = None
            result[f"{key}_status"] = "ERROR"
        result["Reset_status"] = "ERROR"
 
    return result
 
 
# ================================================================
# SECONDARY CHECKS: CLOCK AND REPORT
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
            "Report_missing_variables": None,
            "Report_status": "ERROR",
        }
    report = reports[0]
    events = report.get("EventNames") or []
    variables = report.get("VariableNames") or []
    missing = [v for v in REPORT_REQUIRED_VARIABLES if v not in variables]
    return {
        "Report_EventNames": " | ".join(events),
        "Report_missing_variables": " | ".join(missing),
        "Report_status": status(events == REPORT_EVENT_TARGET and not missing),
    }
 
 
# ================================================================
# OVERALL STATUS
# ================================================================
 
def calculate_overall(soil_result, management_result,
                      clock_result, report_result):
 
    statuses = [
        soil_result["PAW_status"],
        soil_result["NO3_status"],
        soil_result["NH4_status"],
        soil_result["Site_status"],
        management_result["SowDate_status"],
        management_result["Reset_status"],
    ]
    if CHECK_CLOCK:
        statuses.append(clock_result["Clock_status"])
    if CHECK_REPORT:
        statuses.append(report_result["Report_status"])
 
    if any(s == "ERROR" for s in statuses):
        return "ERROR"
    return "OK" if all(s == "OK" for s in statuses) else "CHECK"
 
 
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
print("APSIM INITIAL CONDITIONS AND MANAGEMENT AUDIT")
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
 
            overall = calculate_overall(
                soil_result, management_result,
                clock_result, report_result
            )
 
            # ---------------- Print ----------------
            print(
                f"  Soil {soil_number}: "
                f"PAW={fmt(soil_result['PAW_mm'])} of "
                f"{fmt(soil_result['PAW_capacity_mm'])} mm "
                f"({fmt(soil_result['PAW_percent_full'])}% full) "
                f"[{soil_result['PAW_status']}] | "
                f"NO3={fmt(soil_result['NO3_kg_ha'])} "
                f"{soil_result['NO3_units']} [{soil_result['NO3_status']}] | "
                f"NH4={fmt(soil_result['NH4_kg_ha'])} "
                f"{soil_result['NH4_units']} [{soil_result['NH4_status']}]"
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
                f"    Sowing: SowDate={management_result['SowDate']} "
                f"[{management_result['SowDate_status']}]"
            )
            print(
                "    Reset on date: "
                + " | ".join(
                    f"{k}={management_result[k]} "
                    f"[{management_result[k + '_status']}]"
                    for k in RESET_PARAMETERS
                )
                + f" | Enabled={management_result['Reset_Enabled']}"
                f" -> Reset [{management_result['Reset_status']}]"
            )
            if CHECK_CLOCK:
                print(
                    f"    Clock: {clock_result['Clock_Start']} -> "
                    f"{clock_result['Clock_End']} "
                    f"[{clock_result['Clock_status']}]"
                )
            if CHECK_REPORT:
                print(
                    f"    Report: Events={report_result['Report_EventNames']} "
                    f"[{report_result['Report_status']}]"
                )
            print(f"    OVERALL = {overall}")
 
            # ---------------- CSV row ----------------
            row = {"file": relative_filename, "soil_number": soil_number}
            row.update(soil_result)
            row.update(management_result)
            if CHECK_CLOCK:
                row.update(clock_result)
            if CHECK_REPORT:
                row.update(report_result)
            row["OVERALL"] = overall
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
 