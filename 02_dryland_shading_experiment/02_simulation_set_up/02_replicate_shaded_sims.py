import os
import shutil
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

TEMPLATE_DIR = cfg.DRYLAND_APSIMX_TEMPLATES_FOR_DUPLICATION_DIR

insite = sys.argv[1]

SOURCE_FILE_PATH = os.path.join(
    TEMPLATE_DIR,
    ""+insite+"_2024_radiation_drylandshading_67_128_SpringVQQ.apsimx"
)

OUTPUT_DIRECTORY = cfg.DRYLAND_APSIM_SIMULATIONS_DIR # Optional: leave as None to use source file directory

def replicate_apsim_files(source_file, output_directory=None):
    """
    Replicate APSIM files with different day-of-year values and shift types.
    
    Args:
        source_file (str): Path to the source .apsimx file
        output_directory (str): Directory to save the new files (optional, uses source directory if None)
    """
    
    # Check if source file exists
    if not os.path.exists(source_file):
        print(f"Error: Source file '{source_file}' not found.")
        return
    
    # Parse the filename
    base_name = os.path.basename(source_file)
    source_dir = os.path.dirname(source_file) if output_directory is None else output_directory
    
    # Ensure output directory exists
    if not os.path.exists(source_dir):
        os.makedirs(source_dir)
    
    # Extract components from filename: site_year_variable_shift_percentchange_doy.apsimx
    name_parts = base_name.replace('.apsimx', '').split('_')
    
    if len(name_parts) != 7:
        print(f"Error: Filename doesn't match expected format 'site_year_variable_shift_percentchange_doy_cultivar.apsimx'")
        print(f"Found {len(name_parts)} parts: {name_parts}")
        return
    
    site, year, variable, shift, percentchange, original_doy, cultivar = name_parts
    
    print(f"Processing file: {base_name}")
    print(f"Parsed components: site={site}, year={year}, variable={variable}, shift={shift}, percentchange={percentchange}, doy={original_doy}, cultivar={cultivar}")
    
    year_range =range(1995, 2025)
    shifts = ['drylandshading']
    doy_range = range(128, 366)
    cultivars = ["SpringVQQ","SpringQ", "SpringQM", "SpringM", "SpringMS", "SpringS", "SpringSVS", "SpringVS", 
                 "WinterVQ", "WinterQ", "WinterM", "WinterVS",]  

    # cultivars = ["SpringQM"]      
    
    files_created = 0
    for year in year_range:
        for shift_type in shifts:
            for doy in doy_range:
                for cultivar in cultivars:
                    # Create new filename
                    new_filename = f"{site}_{year}_{variable}_{shift_type}_{percentchange}_{doy:03d}_{cultivar}.apsimx"
                    new_filepath = os.path.join(source_dir, new_filename)
                
                    try:
                        # Copy the source file to new location
                        shutil.copy2(source_file, new_filepath)
                        files_created += 1
                    
                        # Print progress every 50 files
                        if files_created % 50 == 0:
                            print(f"Created {files_created} files...")
                        
                    except Exception as e:
                        print(f"Error creating file {new_filename}: {e}")
    
        print(f"\nCompleted! Created {files_created} files.")
        print(f"Files saved in: {source_dir}")
    
        # Summary
        total_doys = len(doy_range)
        total_shifts = len(shifts)
        total_years = len(year_range)
        total_cultivars = len(cultivars)
        expected_files = total_doys * total_shifts * total_years * total_cultivars

        print(f"\nSummary:")
        print(f"- Year range: {min(year_range)} to {max(year_range)} ({total_years} years)")
        print(f"- DOY range: {min(doy_range)} to {max(doy_range)} ({total_doys} days)")
        print(f"- Shift types: {', '.join(shifts)} ({total_shifts} types)")
        print(f"- Cultivar types: {', '.join(cultivars)} ({total_cultivars} types)")
        print(f"- Expected files: {expected_files}")
        print(f"- Files created: {files_created}")



# Example usage
if __name__ == "__main__":
    # Use the configured paths
    replicate_apsim_files(SOURCE_FILE_PATH, OUTPUT_DIRECTORY)
    
    # Alternative: specify paths directly in the function call
    # replicate_apsim_files(
    #     source_file="/full/path/to/lameroo_2024_radiation_decrease_33_135.apsimx",
    #     output_directory="/full/path/to/output/directory"
    # )


# --- Final usage and timing ---
print_usage("End")
end_time = time.time()
elapsed = end_time - start_time
print(f"Total runtime: {elapsed:.2f} seconds")
print("This script ended running at:", datetime.datetime.now())