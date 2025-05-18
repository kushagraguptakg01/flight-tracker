# generate_markdown.py
import json
from datetime import datetime, date, timedelta
import os
import sys

def format_price(price_value):
    if price_value is None:
        return "N/A"
    if isinstance(price_value, (int, float)) and price_value == 0.0:
        return "<span style='color:grey;'>₹0</span>" # Special styling for 0
    try:
        return f"₹{float(price_value):,.0f}"
    except (ValueError, TypeError):
        return "N/A"

def get_price_trend_emoji(trend_str):
    if trend_str is None or trend_str == "N/A" or trend_str == "unknown":
        return " "
    trend_str = str(trend_str).lower()
    if "low" in trend_str: return "📉 (Low)"
    if "high" in trend_str: return "📈 (High)"
    if "typical" in trend_str: return "📊 (Typical)"
    return f"{trend_str.capitalize()}"

def extract_time(time_str_full):
    if " on " in time_str_full:
        return time_str_full.split(" on ")[0]
    return time_str_full

def format_timestamp_to_date(iso_timestamp_str):
    if not iso_timestamp_str:
        return "N/A"
    try:
        dt_obj = datetime.fromisoformat(iso_timestamp_str.replace('Z', '+00:00')) # Handle Z for UTC
        return dt_obj.strftime('%Y-%m-%d') # Just the date part
    except (ValueError, TypeError):
        return "N/A" # Or return original string if preferred

def generate_route_markdown(json_filepath):
    """Generates a markdown section for a single route's data."""
    base_filename = os.path.basename(json_filepath)
    if not os.path.exists(json_filepath):
        return f"### Data for {base_filename}\n\n_File not found._\n\n---\n"

    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return f"### Data for {base_filename}\n\n_Error decoding JSON._\n\n---\n"
    except Exception as e:
        return f"### Data for {base_filename}\n\n_Error reading file: {e}_\n\n---\n"

    meta_info = data.get("meta_info", {})
    origin = meta_info.get("origin", "N/A")
    destination = meta_info.get("destination", "N/A")
    last_run_iso = meta_info.get("script_last_successful_run_timestamp")
    last_run_display = "N/A"
    if last_run_iso:
        try:
            last_run_dt = datetime.fromisoformat(last_run_iso)
            last_run_display = last_run_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except ValueError:
            last_run_display = last_run_iso

    md_section = f"## ✈️ Flight Prices: {origin} ➔ {destination}\n"
    md_section += f"_Last data update for this route: {last_run_display}_\n\n"

    quick_view_data = data.get("lowest_price_quick_view", {})
    tracked_dates_data = data.get("tracked_flight_dates", {})

    if not quick_view_data:
        md_section += "No flight price data available in 'lowest_price_quick_view'.\n\n---\n"
        return md_section

    # Added "Lowest Found On" column
    md_section += "| Flight Date   | Day | Lowest Price | Dep → Arr (Cheapest)    | Airline     | Duration   | Stops | Lowest Found On | Price Trend |\n"
    md_section += "|-----------------|-----|--------------|-------------------------|-------------|------------|-------|-----------------|-------------|\n"

    entries_processed = 0
    sorted_flight_dates = sorted(quick_view_data.keys())

    for flight_date_str in sorted_flight_dates:
        entries_processed +=1
        details = quick_view_data[flight_date_str]
        day_of_week_full = details.get("day_of_week", "N/A")
        day_of_week_short = day_of_week_full[:3] if day_of_week_full != "N/A" else "N/A"

        numeric_price = details.get("numeric_price")
        flight_info = details.get("flight_details")
        error_msg = details.get("error")
        first_recorded_at_ts = details.get("first_recorded_at") # Get the timestamp
        lowest_price_found_date_display = format_timestamp_to_date(first_recorded_at_ts) # Format it

        price_display = format_price(numeric_price)
        flight_times_desc = "N/A"
        airline = "N/A"
        duration = "N/A"
        stops_val = "N/A"
        google_trend_val = " "

        if error_msg:
            flight_times_desc = f"<span style='color:orange;'>Error: {error_msg}</span>"
            lowest_price_found_date_display = "N/A" # No valid price found on any date
        elif flight_info:
            airline = flight_info.get("name", "N/A")
            dep_time_full = flight_info.get("departure_time", "N/A")
            arr_time_full = flight_info.get("arrival_time", "N/A")
            arr_ahead = flight_info.get("arrival_time_ahead", "")

            dep_time_short = extract_time(dep_time_full)
            arr_time_short = extract_time(arr_time_full)
            flight_times_desc = f"{dep_time_short} → {arr_time_short}{arr_ahead}"

            duration = flight_info.get("duration_str", "N/A")
            stops_val = str(flight_info.get("stops", "N/A"))
        elif numeric_price is not None: # Price exists (e.g. 0), but no flight_info
            flight_times_desc = "_Details unavailable_"
            if numeric_price == 0.0:
                 flight_times_desc = "<span style='color:grey;'>_Likely Canceled/Error_</span>"
            # lowest_price_found_date_display would still be valid if numeric_price is 0 and has a timestamp
        else: # No error, no flight_info, no numeric_price
            flight_times_desc = "_No data found_"
            lowest_price_found_date_display = "N/A"


        if flight_date_str in tracked_dates_data: # For Google Trend
            latest_snapshot = tracked_dates_data[flight_date_str].get("latest_check_snapshot", {})
            google_trend_val = get_price_trend_emoji(latest_snapshot.get("google_price_trend"))

        # Renamed "Flight Date" to make it clear it's the date of travel
        md_section += f"| {flight_date_str}   | {day_of_week_short} | {price_display} | {flight_times_desc} | {airline} | {duration} | {stops_val} | {lowest_price_found_date_display} | {google_trend_val} |\n"

    if entries_processed == 0:
        md_section += "| N/A             | N/A | N/A          | No data rows found.     | N/A         | N/A        | N/A   | N/A             |        |\n"

    md_section += "\n---\n"
    return md_section

# --- (Function: generate_master_markdown - remains IDENTICAL) ---
def generate_master_markdown(json_files, output_md_file):
    master_md_content = f"# Flight Price Summary ✈️\n\n"
    master_md_content += f"_{{This README is automatically updated by a GitHub Action. Last generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}}}_\n\n"
    master_md_content += "This page shows the latest tracked flight prices for configured routes. Prices are for one adult, economy, one-way, in INR.\n\n"
    processed_any_valid_file = False
    for json_file_path in json_files:
        if os.path.exists(json_file_path):
            print(f"Processing {json_file_path} for Markdown report...")
            master_md_content += generate_route_markdown(json_file_path)
            processed_any_valid_file = True
        else:
            print(f"Warning: JSON file {json_file_path} not found. Skipping for Markdown report.")
            master_md_content += f"## Data for {os.path.basename(json_file_path)}\n\n_File not found during Markdown generation._\n\n---\n"
    if not processed_any_valid_file and json_files:
        master_md_content += "\n_No valid data files were found or processed successfully from the provided list._\n"
    elif not json_files:
        master_md_content += "\n_No data files specified for processing._\n"
    master_md_content += "\n\n---\nPowered by [GitHub Actions](https://github.com/features/actions) and Python.\n"
    try:
        with open(output_md_file, 'w', encoding='utf-8') as f:
            f.write(master_md_content)
        print(f"Markdown report successfully generated at {output_md_file}")
    except Exception as e:
        print(f"Error writing markdown file {output_md_file}: {e}")
        return False
    return True

# --- (if __name__ == "__main__": block - remains IDENTICAL) ---
if __name__ == "__main__":
    if len(sys.argv) > 1:
        output_filename_arg = sys.argv[1]
        json_files_args = sys.argv[2:]
        if not json_files_args:
             print("Usage: python generate_markdown.py <output_markdown_file.md> [input_json_file1.json input_json_file2.json ...]")
             print("No JSON files provided as arguments. Discovering flight_tracker_*.json files locally.")
             json_files_args = [f for f in os.listdir('.') if f.startswith("flight_tracker_") and f.endswith(".json")]
    else:
        print("Usage: python generate_markdown.py <output_markdown_file.md> [input_json_file1.json ...]")
        output_filename_arg = "README.md"
        print(f"Defaulting to {output_filename_arg} and discovering JSON files locally.")
        json_files_args = [f for f in os.listdir('.') if f.startswith("flight_tracker_") and f.endswith(".json")]
    if not json_files_args:
        print("No flight_tracker_*.json files found to process.")
        sys.exit(0)
    print(f"Found JSON files for report: {json_files_args}")
    print(f"Output Markdown to: {output_filename_arg}")
    if not generate_master_markdown(json_files_args, output_filename_arg):
        sys.exit(1)