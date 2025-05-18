# /generate_markdown.py
import json
from datetime import datetime, date, timedelta, timezone # Import timezone
import os
import sys
import pytz # For timezone conversion

# --- Helper Functions ---
def format_price(price_value):
    if price_value is None:
        return "N/A"
    if isinstance(price_value, (int, float)) and price_value == 0.0:
        return "<span style='color:grey;'>₹0</span>"
    try:
        return f"₹{float(price_value):,.0f}"
    except (ValueError, TypeError):
        return "N/A"

def get_price_trend_emoji(trend_str):
    if trend_str is None or trend_str == "N/A" or trend_str == "unknown":
        return " " # Use non-breaking space for alignment
    trend_str = str(trend_str).lower()
    if "low" in trend_str: return "📉 (Low)"
    if "high" in trend_str: return "📈 (High)"
    if "typical" in trend_str: return "📊 (Typical)"
    return f"{trend_str.capitalize()}"

def extract_time(time_str_full):
    if not time_str_full: return "N/A" # Handle None or empty string
    if " on " in time_str_full:
        return time_str_full.split(" on ")[0]
    return time_str_full

def format_iso_timestamp_to_ist_string(iso_timestamp_str, include_time=True):
    """Converts an ISO timestamp string to a human-readable IST date/time string."""
    if not iso_timestamp_str:
        return "N/A"
    try:
        # Parse the ISO string.
        # datetime.fromisoformat() handles strings with 'Z' or '+HH:MM' offsets.
        # If it's naive (no offset), we assume it's UTC as per our script's convention.
        dt_obj = datetime.fromisoformat(iso_timestamp_str.replace('Z', '+00:00'))

        # If the parsed datetime object is naive (no tzinfo), assume it's UTC.
        if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
            dt_utc = pytz.utc.localize(dt_obj)
        else:
            dt_utc = dt_obj.astimezone(pytz.utc) # Ensure it's UTC if it had another offset

        ist_timezone = pytz.timezone('Asia/Kolkata')
        dt_ist = dt_utc.astimezone(ist_timezone)
        
        if include_time:
            return dt_ist.strftime('%Y-%m-%d %H:%M:%S IST')
        else:
            return dt_ist.strftime('%Y-%m-%d') # Just the date part in IST
            
    except (ValueError, TypeError, AttributeError) as e:
        print(f"Warning: Could not parse or convert timestamp '{iso_timestamp_str}': {e}")
        return "N/A"

def get_lowest_price_and_details_in_period(observations_history, period_days, today_date):
    """
    Finds the lowest price and its corresponding flight details for a specific travel date
    from observations made within the last 'period_days'.
    Returns a tuple: (min_price, flight_details_dict, observation_date_ist_str)
    """
    if not observations_history:
        return None, None, None

    min_price_in_period = float('inf')
    best_flight_details = None
    observation_timestamp_of_best_price_utc_iso = None # Store the original UTC timestamp
    found_any_in_period = False
    
    # Cutoff date is (today - period_days + 1 day) to include 'period_days' ago up to today.
    # Example: period_days = 7. today - 7 + 1 = today - 6 days.
    # So, if today is 10th, cutoff is 4th. Dates >= 4th are included (4,5,6,7,8,9,10 is 7 days)
    cutoff_date = today_date - timedelta(days=period_days - 1)

    for obs in observations_history:
        # --- BUG FIX: Corrected keys ---
        check_timestamp_str = obs.get("checked_at") # Corrected from "check_timestamp"
        if not check_timestamp_str:
            continue
        
        try:
            # Parse the UTC timestamp from the observation
            obs_datetime_utc = datetime.fromisoformat(check_timestamp_str.replace('Z', '+00:00'))
            # We need to compare the *date* part of the observation with our cutoff
            # For consistency, ensure obs_datetime_utc is timezone-aware UTC
            if obs_datetime_utc.tzinfo is None or obs_datetime_utc.tzinfo.utcoffset(obs_datetime_utc) is None:
                obs_datetime_utc = pytz.utc.localize(obs_datetime_utc)
            else:
                obs_datetime_utc = obs_datetime_utc.astimezone(pytz.utc)
            
            obs_date_utc = obs_datetime_utc.date() # Get the date part in UTC

            # Check if the observation's UTC date falls within our desired window relative to 'today_date' (which is also a date object)
            if obs_date_utc >= cutoff_date and obs_date_utc <= today_date:
                # --- BUG FIX: Corrected key ---
                cheapest_flight_in_check = obs.get("cheapest_flight_found") # Corrected from "cheapest_flight_in_this_check"
                if cheapest_flight_in_check:
                    numeric_price = cheapest_flight_in_check.get("numeric_price")
                    if numeric_price is not None and numeric_price < min_price_in_period:
                        min_price_in_period = numeric_price
                        best_flight_details = cheapest_flight_in_check.get("flight_details")
                        observation_timestamp_of_best_price_utc_iso = check_timestamp_str # Store the original UTC ISO
                        found_any_in_period = True
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse observation timestamp '{check_timestamp_str}' in get_lowest_price_and_details_in_period: {e}")
            continue
            
    if found_any_in_period:
        # Convert the UTC timestamp of the best price to IST string here
        obs_date_ist_str = format_iso_timestamp_to_ist_string(observation_timestamp_of_best_price_utc_iso)
        return min_price_in_period, best_flight_details, obs_date_ist_str
    return None, None, None


def generate_route_markdown(json_filepath, today_date):
    base_filename = os.path.basename(json_filepath)
    if not os.path.exists(json_filepath):
        return f"### Data for {base_filename}\n\n_File not found._\n"
    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return f"### Data for {base_filename}\n\n_Error loading/parsing {json_filepath}: {e}_\n"

    meta_info = data.get("meta_info", {})
    origin = meta_info.get("origin", "N/A")
    destination = meta_info.get("destination", "N/A")
    last_run_iso = meta_info.get("script_last_successful_run_timestamp")
    last_run_display_ist = format_iso_timestamp_to_ist_string(last_run_iso) # Convert to IST

    md_section = f"## ✈️ Flight Prices: {origin} ➔ {destination}\n"
    md_section += f"_Last data update for this route: {last_run_display_ist}_\n\n"

    quick_view_data = data.get("lowest_price_quick_view", {})
    tracked_dates_data = data.get("tracked_flight_dates", {})

    # --- Main Table: Overall Lowest Prices Ever Recorded ---
    md_section += "### Current Overall Lowest Prices by Travel Date\n"
    if not quick_view_data:
        md_section += "_No overall lowest price data available._\n"
    else:
        md_section += "| Flight Date   | Day | Price | Dep → Arr (Details) | Airline | Duration | Stops | Found On (IST)    | Trend |\n"
        md_section += "|-----------------|-----|-------|-----------------------|---------|----------|-------|-------------------|-------|\n"
        sorted_overall_dates = sorted(quick_view_data.keys())
        for flight_date_str in sorted_overall_dates:
            details = quick_view_data[flight_date_str]
            day_full = details.get("day_of_week", "N/A")
            day_short = day_full[:3] if day_full != "N/A" else "N/A"
            price = details.get("numeric_price")
            flight_info = details.get("flight_details")
            error_msg = details.get("error")
            # "first_recorded_at" from quick_view is the timestamp of when this overall lowest was first seen
            found_on_ist = format_iso_timestamp_to_ist_string(details.get("first_recorded_at")) # Convert to IST
            
            price_disp = format_price(price)
            flight_desc, airline, duration, stops_val = "N/A", "N/A", "N/A", "N/A"

            if error_msg:
                flight_desc = f"<span style='color:orange;'>Error: {error_msg}</span>"
            elif flight_info:
                airline = flight_info.get("name", "N/A")
                dep = extract_time(flight_info.get("departure_time", "N/A"))
                arr = extract_time(flight_info.get("arrival_time", "N/A"))
                arr_ahead = flight_info.get("arrival_time_ahead", "")
                flight_desc = f"{dep} → {arr}{arr_ahead if arr_ahead else ''}" # Ensure arr_ahead is not None
                duration = flight_info.get("duration_str", "N/A")
                stops_val = str(flight_info.get("stops", "N/A"))
            elif price is not None: # Price exists (e.g. 0), but no flight_info
                flight_desc = "_Details unavailable_"
                if price == 0.0:
                    flight_desc = "<span style='color:grey;'>_Likely Canceled/Error_</span>"
            else: # No error, no flight_info, no numeric_price
                flight_desc = "_No data found_"

            trend_val = " " # Default
            if flight_date_str in tracked_dates_data:
                latest_snap = tracked_dates_data[flight_date_str].get("latest_check_snapshot", {})
                trend_val = get_price_trend_emoji(latest_snap.get("google_price_trend"))
            
            md_section += f"| {flight_date_str}   | {day_short} | {price_disp} | {flight_desc} | {airline} | {duration} | {stops_val} | {found_on_ist} | {trend_val} |\n"
    md_section += "\n"

    # --- Recently Observed Prices Tables ---
    if tracked_dates_data: # Need this for historical observations
        for period_days, period_title_suffix in [(7, "Last 7 Days"), (14, "Last 14 Days")]:
            md_section += f"### Lowest Prices Observed in {period_title_suffix} (For This Route)\n"
            md_section += "_For each travel date, shows the cheapest price seen if an observation for that travel date occurred in this period._\n" # Clarified description
            
            recent_observations_table_content = ""
            table_header = "| Travel Date | Day | Price | Dep → Arr (Details) | Airline | Duration | Stops | Observed On (IST) |\n"
            table_separator = "|-------------|-----|-------|-----------------------|---------|----------|-------|-------------------|\n"
            
            rows_for_period_table = 0
            sorted_tracked_dates = sorted(tracked_dates_data.keys()) # Iterate through all travel dates

            for flight_date_str in sorted_tracked_dates:
                date_specific_tracking_info = tracked_dates_data[flight_date_str]
                day_full = date_specific_tracking_info.get("day_of_week", "N/A") # Get day from tracked_dates
                day_short = day_full[:3] if day_full != "N/A" else "N/A"
                
                observations_history = date_specific_tracking_info.get("hourly_observations_history", [])
                
                # Get the lowest price & details for THIS flight_date_str observed in the period
                price, flight_info, obs_date_ist_str = get_lowest_price_and_details_in_period(
                    observations_history, period_days, today_date
                )

                if price is not None: # If a price was found in this period for this specific travel date
                    rows_for_period_table += 1
                    price_disp = format_price(price)
                    flight_desc, airline, duration, stops_val = "N/A", "N/A", "N/A", "N/A"

                    if flight_info: # Details of the flight corresponding to this recently observed price
                        airline = flight_info.get("name", "N/A")
                        dep = extract_time(flight_info.get("departure_time", "N/A"))
                        arr = extract_time(flight_info.get("arrival_time", "N/A"))
                        arr_ahead = flight_info.get("arrival_time_ahead", "")
                        flight_desc = f"{dep} → {arr}{arr_ahead if arr_ahead else ''}" # Ensure arr_ahead is not None
                        duration = flight_info.get("duration_str", "N/A")
                        stops_val = str(flight_info.get("stops", "N/A"))
                    else: # Price found, but no details (should be rare if price exists)
                        flight_desc = "_Details N/A_"
                    
                    recent_observations_table_content += f"| {flight_date_str} | {day_short} | {price_disp} | {flight_desc} | {airline} | {duration} | {stops_val} | {obs_date_ist_str} |\n"

            if rows_for_period_table > 0:
                md_section += table_header + table_separator + recent_observations_table_content
            else:
                md_section += f"_No flight prices were observed for any travel date in the {period_title_suffix.lower()}._\n"
            md_section += "\n"
            
    return md_section


def generate_master_markdown(json_files, output_md_file):
    today = date.today()
    # Get current UTC time using the recommended method
    generated_at_utc = datetime.now(timezone.utc) # CORRECTED: Use timezone.utc
    # Convert to ISO format string. isoformat() on aware object includes offset.
    generated_at_ist_str = format_iso_timestamp_to_ist_string(generated_at_utc.isoformat())

    master_md_content = f"# Flight Price Summary ✈️\n\n"
    master_md_content += f"_{{This README is automatically updated. Last generated: {generated_at_ist_str}}}_\n\n" # Use IST
    master_md_content += "This page shows the latest tracked flight prices for configured routes. Prices are for one adult, economy, one-way, in INR. All timestamps are in IST.\n\n"

    processed_any_valid_file = False
    for json_file_path in json_files:
        if os.path.exists(json_file_path):
            print(f"Processing {json_file_path} for Markdown report...")
            master_md_content += generate_route_markdown(json_file_path, today)
            master_md_content += "\n---\n" # Separator after each full route section
            processed_any_valid_file = True
        else:
            print(f"Warning: JSON file {json_file_path} not found. Skipping for Markdown report.")
            master_md_content += f"## Data for {os.path.basename(json_file_path)}\n\n_File not found during Markdown generation._\n\n---\n"

    if not processed_any_valid_file and json_files:
        master_md_content += "\n_No valid data files were found or processed successfully from the provided list._\n"
    elif not json_files:
        master_md_content += "\n_No data files specified for processing._\n"
    master_md_content += "\n\nPowered by [GitHub Actions](https://github.com/features/actions) and Python.\n"
    
    try:
        with open(output_md_file, 'w', encoding='utf-8') as f:
            f.write(master_md_content)
        print(f"Markdown report successfully generated at {output_md_file}")
    except Exception as e:
        print(f"Error writing markdown file {output_md_file}: {e}")
        return False
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        output_filename_arg = sys.argv[1]
        json_files_args = sys.argv[2:]
        if not json_files_args:
             print("Usage: python generate_markdown.py <output_markdown_file.md> [input_json_file1.json ...]")
             print("No JSON files provided as arguments. Discovering flight_tracker_*.json files locally.")
             json_files_args = [f for f in os.listdir('.') if f.startswith("flight_tracker_") and f.endswith(".json")]
    else:
        print("Usage: python generate_markdown.py <output_markdown_file.md> [input_json_file1.json ...]")
        output_filename_arg = "README.md" # Default output file
        print(f"Defaulting to {output_filename_arg} and discovering JSON files locally.")
        json_files_args = [f for f in os.listdir('.') if f.startswith("flight_tracker_") and f.endswith(".json")]

    if not json_files_args:
        print("No flight_tracker_*.json files found to process.")
        sys.exit(0) # Exit gracefully if no files

    print(f"Found JSON files for report: {json_files_args}")
    print(f"Output Markdown to: {output_filename_arg}")

    if not generate_master_markdown(json_files_args, output_filename_arg):
        sys.exit(1) # Error during markdown generation