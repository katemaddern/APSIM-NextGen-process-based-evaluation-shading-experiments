import pandas as pd
import os
from io import StringIO
import time
import psutil
import datetime
import sys
from pathlib import Path

# --- Metadata ---
try:
    print("The script used to generate this output is", os.path.basename(__file__))
    print("The script above can be found in this directory:", os.path.dirname(os.path.abspath(__file__)))
except NameError:
    print("Running in interactive mode; __file__ is not defined.")

print("This script started running at:", datetime.datetime.now())

# --- Timing ---
start_time = time.time()

# --- Memory Usage ---
def print_usage(stage):
    process = psutil.Process(os.getpid())
    mem_MB = process.memory_info().rss / 1024 ** 2
    print(f"{stage} - Memory usage: {mem_MB:.2f} MB")

print_usage("Start")

# Load configuration
SCRIPTS_BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_BASE))

from config_loader import cfg

# Output directory
MET_FILE_OUTPUT = cfg.SHADING_MET_OUT_DIR
os.chdir(MET_FILE_OUTPUT)

# Get MET filename passed from shell script
if len(sys.argv) < 2:
    raise ValueError(
        "No MET file supplied. "
        "Usage: python 02_met_file_radiation_modifer.py <filename.met>"
    )
insite = sys.argv[1]
print(f"Processing MET file: {insite}")

site = insite.split('_')[0]

# Input file
INPUT_MET_DIR = cfg.SHADING_MET_FILES_WITH_CO2
INPUT_MET_FILE = os.path.join(
    INPUT_MET_DIR,
    insite
)

if not os.path.isfile(INPUT_MET_FILE):
    raise FileNotFoundError(
        f"Input MET file not found: {INPUT_MET_FILE}"
    )
print(f"Input file: {INPUT_MET_FILE}")

# Read input file
with open(INPUT_MET_FILE, "r") as f:
    lines = f.readlines()

# Identify header line index
data_start_index = next(i for i, line in enumerate(lines) if line.startswith('year'))
units_line_index = data_start_index + 1

# Get metadata header, column names, and units line
header_lines = lines[:data_start_index]  # all lines before column names
column_header = lines[data_start_index]
units_line = lines[units_line_index]
data_lines = lines[units_line_index + 1:]  # skip units row

# Read data into a DataFrame
column_names = column_header.strip().split()
data = pd.read_csv(StringIO(''.join(data_lines)), sep=r'\s+', names=column_names)

# Ensure numeric types for processing
data['day'] = pd.to_numeric(data['day'], errors='coerce')
data['radn'] = pd.to_numeric(data['radn'], errors='coerce')
data['maxt'] = pd.to_numeric(data['maxt'], errors='coerce')
data['mint'] = pd.to_numeric(data['mint'], errors='coerce')
data['year'] = pd.to_numeric(data['year'], errors='coerce')

# Drop any rows where year/day couldn't be parsed (e.g., stray text lines)
data = data.dropna(subset=['year', 'day']).copy()

# Build a proper date so ranges can cross the year boundary
data['date'] = (
    pd.to_datetime(data['year'].astype(int).astype(str), format='%Y')
    + pd.to_timedelta(data['day'].astype(int) - 1, unit='D')
)

# Store original radiation values for reference
data['original_radn'] = data['radn'].copy()

# Process and write output for each year and day combination
for current_year in range(1995, 2025, 1):
    # Simulation period: 1 Jan of current year to 1 Mar of the following year (inclusive)
    period_start = pd.Timestamp(current_year, 1, 1)
    period_end = pd.Timestamp(current_year + 1, 3, 1)

    year_data = data[(data['date'] >= period_start) & (data['date'] <= period_end)].copy()

    if year_data.empty:
        print(f"Warning: No data found for {period_start.date()} to {period_end.date()}")
        continue

    if year_data['date'].max() < period_end:
        print(f"Warning: Data for {current_year} ends at {year_data['date'].max().date()}, "
              f"before {period_end.date()}")

    for current_day in range(128, 366, 1):
        # Create a fresh copy for each day modification
        df = year_data.copy()

        # Reset radiation to original values
        df['radn'] = df['original_radn'].copy()

        # Define the shading window (target day ±7 days) using real dates,
        # so windows near the end of the year can extend into January
        target_date = period_start + pd.Timedelta(days=current_day - 1)
        start_date = target_date - pd.Timedelta(days=7)
        end_date = target_date + pd.Timedelta(days=7)

        # Shading window: 14 days total (target day -7 to +6 inclusive).
        # end_date is excluded by '<'; 
        mask = (df['date'] >= start_date) & (df['date'] < end_date)

        # Apply 67% shading intensity which is 67% of radiation NOT making it to the crop canopy
        # Therefore that is 33% of the radiation making it to the canopy
        df.loc[mask, 'radn'] = df.loc[mask, 'radn'] * 0.33

        # Quality check: ensure radiation values are reasonable
        if df['radn'].max() > 50:  # Flag unreasonable values
            print(f"Warning: High radiation values detected for year {current_year}, day {current_day}")
            print(f"Max radiation: {df['radn'].max():.2f} MJ/m²/day")

        # Remove the helper columns before output
        df = df.drop(columns=['original_radn', 'date'])

        # Generate output filename
        output_filename = f'{site}_{current_year}_radiation_shading_67_{current_day}.met'

        # Write output file
        with open(output_filename, 'w') as f:
            f.writelines(header_lines)      # Write metadata
            f.write(column_header)          # Write column names
            f.write(units_line)             # Write units line

            # Write data with proper formatting
            for _, row in df.iterrows():
                # Format each row manually to maintain proper spacing and precision
                line = f"{int(row['year'])}\t{int(row['day'])}\t{row['radn']:.2f}\t"
                line += f"{row['maxt']:.2f}\t{row['mint']:.2f}\t{row['rain']:.2f}\t"
                line += f"{row['evap']:.2f}\t{row['vp']:.2f}\t{row['code']}\t{row['co2']:.2f}\n"
                f.write(line)

print("Processing completed successfully!")

# Optional: Print some statistics for verification
print(f"\nProcessed years: {list(range(1995, 2025))}")
print("Simulation period per file: 1 Jan of each year to 1 Mar of the following year")
print(f"Day range for modifications: 128-365 (±7 days around each target day)")
print(f"Radiation shading factor: 67% shading intensity = 67% decrease = radiation multiplied by 0.33")

# --- Final usage and timing ---
print_usage("End")
end_time = time.time()
elapsed = end_time - start_time
print(f"Total runtime: {elapsed:.2f} seconds")
print("This script ended running at:", datetime.datetime.now())