# /generate_markdown.py
import json
from datetime import datetime, date, timedelta, timezone
import os
import sys
import pytz

# --- Helper Functions (format_price, get_price_trend_emoji, extract_time, format_iso_timestamp_to_ist_string) ---
def format_price(price_value):
    if price_value is None:
        return "N/A"
    if isinstance(price_value, (int, float)) and price_value == 0.0:
        # This case might not be hit if flight.py filters out 0.0 prices by setting them to None
        return "<span style='color:grey;'>₹0</span>"
    try:
        return f"₹{float(price_value):,.0f}"
    except (ValueError, TypeError):
        return "N/A"

def get_price_trend_emoji(trend_str):
    if trend_str is None or trend_str == "N/A" or trend_str == "unknown":
        return " "
    trend_str = str(trend_str).lower()
    if "low" in trend_str: return "📉 (Low)"
    if "high" in trend_str: return "📈 (High)"
    if "typical" in trend_str: return "📊 (Typical)"
    return f"{trend_str.capitalize()}"

def extract_time(time_str_full):
    if not time_str_full: return "N/A"
    if " on " in time_str_full:
        return time_str_full.split(" on ")[0]
    return time_str_full

def format_iso_timestamp_to_ist_string(iso_timestamp_str, include_time=True):
    if not iso_timestamp_str:
        return "N/A"
    try:
        # Parse the ISO timestamp string. 
        # .replace('Z', '+00:00') handles UTC 'Z' notation correctly, making it offset-aware.
        dt_obj = datetime.fromisoformat(iso_timestamp_str.replace('Z', '+00:00'))

        # Check if the datetime object is naive (no timezone info) or aware.
        if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
            # If naive, assume it's UTC and make it UTC-aware.
            # This is based on the expectation that timestamps from flight.py are UTC.
            dt_utc = pytz.utc.localize(dt_obj)
        else:
            # If aware (e.g., already UTC or with another offset), convert it to UTC to normalize.
            dt_utc = dt_obj.astimezone(pytz.utc)
        
        # Define the IST timezone.
        ist_timezone = pytz.timezone('Asia/Kolkata')
        # Convert the UTC datetime to IST.
        dt_ist = dt_utc.astimezone(ist_timezone)
        
        if include_time:
            return dt_ist.strftime('%Y-%m-%d %H:%M:%S IST')
        else:
            return dt_ist.strftime('%Y-%m-%d')
    except (ValueError, TypeError, AttributeError) as e:
        print(f"Warning: Could not parse or convert timestamp '{iso_timestamp_str}': {e}")
        return "N/A"

def get_lowest_price_and_details_in_period(observations_history, period_days, today_date):
    if not observations_history:
        return None, None, None
    min_price_in_period = float('inf')
    best_flight_details = None
    observation_timestamp_of_best_price_utc_iso = None
    found_any_in_period = False
    cutoff_date = today_date - timedelta(days=period_days - 1) # e.g. for 7 days, today - 6 days
    for obs in observations_history:
        check_timestamp_str = obs.get("checked_at")
        if not check_timestamp_str:
            continue
        try:
            # Parse the ISO timestamp string from the observation.
            # .replace('Z', '+00:00') ensures UTC 'Z' notation is handled, making it offset-aware.
            obs_datetime_aware = datetime.fromisoformat(check_timestamp_str.replace('Z', '+00:00'))

            # Ensure the timestamp is in UTC.
            # If it's naive (no timezone info), assume it's UTC and make it aware.
            if obs_datetime_aware.tzinfo is None or obs_datetime_aware.tzinfo.utcoffset(obs_datetime_aware) is None:
                obs_datetime_utc = pytz.utc.localize(obs_datetime_aware)
            # If it's already aware (e.g., from 'Z' or another offset), normalize to UTC.
            else:
                obs_datetime_utc = obs_datetime_aware.astimezone(pytz.utc)
            
            # Extract the calendar date part (year, month, day) from the UTC timestamp.
            # Note: .date() on an aware datetime returns a naive date, but representing the date in that timezone (here, UTC).
            obs_date_utc = obs_datetime_utc.date()

            # Compare the UTC date of the observation with the period defined by local dates (today_date, cutoff_date).
            # `today_date` is date.today() (local machine's date).
            # `cutoff_date` is derived from `today_date`.
            # This comparison means we are checking if the *UTC calendar date* of the observation
            # falls within the *local calendar date* range. This is generally acceptable for daily granularity.
            if obs_date_utc >= cutoff_date and obs_date_utc <= today_date:
                cheapest_flight_in_check = obs.get("cheapest_flight_found")
                if cheapest_flight_in_check:
                    numeric_price = cheapest_flight_in_check.get("numeric_price")
                    # Only consider positive prices
                    if numeric_price is not None and numeric_price > 0 and numeric_price < min_price_in_period:
                        min_price_in_period = numeric_price
                        best_flight_details = cheapest_flight_in_check.get("flight_details")
                        observation_timestamp_of_best_price_utc_iso = check_timestamp_str
                        found_any_in_period = True
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse observation timestamp '{check_timestamp_str}' in get_lowest_price_and_details_in_period: {e}")
            continue
            
    if found_any_in_period:
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
    last_run_display_ist = format_iso_timestamp_to_ist_string(last_run_iso)

    md_section = f"## ✈️ Flight Prices: {origin} ➔ {destination}\n"
    md_section += f"_Last data update for this route: {last_run_display_ist}_\n\n"

    quick_view_data = data.get("lowest_price_quick_view", {})
    tracked_dates_data = data.get("tracked_flight_dates", {})

    # --- Main Table: Overall Lowest Prices Ever Recorded ---
    md_section += "### Current Overall Lowest Prices by Travel Date\n"
    if not quick_view_data:
        md_section += "_No overall lowest price data available._\n"
    else:
        md_section += "| Flight Date   | Day | Lowest Ever | Current Price | Dep → Arr (Details) | Airline | Duration | Stops | Found On (IST)    | Trend |\n"
        md_section += "|-----------------|-----|-------------|---------------|-----------------------|---------|----------|-------|-------------------|-------|\n"
        sorted_overall_dates = sorted(quick_view_data.keys())
        for flight_date_str in sorted_overall_dates:
            details = quick_view_data[flight_date_str]
            day_full = details.get("day_of_week", "N/A")
            day_short = day_full[:3] if day_full != "N/A" else "N/A"
            overall_lowest_price = details.get("numeric_price")
            flight_info_overall = details.get("flight_details") # This is the flight_details for the "Lowest Ever" price
            error_msg_overall = details.get("error") # Error associated with the "Lowest Ever" price/entry
            found_on_ist = format_iso_timestamp_to_ist_string(details.get("first_recorded_at"))
            overall_lowest_price_disp = format_price(overall_lowest_price)
            
            flight_desc, airline, duration, stops_val = "N/A", "N/A", "N/A", "N/A"

            if error_msg_overall: # If the quick_view entry itself is an error placeholder
                flight_desc = f"<span style='color:orange;'>{error_msg_overall}</span>"
            elif flight_info_overall:
                airline = flight_info_overall.get("name", "N/A")
                dep = extract_time(flight_info_overall.get("departure", "N/A"))
                arr = extract_time(flight_info_overall.get("arrival", "N/A"))
                arr_ahead = flight_info_overall.get("arrival_time_ahead", "")
                flight_desc = f"{dep} → {arr}{arr_ahead if arr_ahead else ''}"
                duration = flight_info_overall.get("duration", "N/A")
                stops_val = str(flight_info_overall.get("stops", "N/A"))
            elif overall_lowest_price is not None: # Has a price, but no details (should be rare)
                flight_desc = "_Details unavailable_"
                if overall_lowest_price == 0.0: # Handled by format_price, but good to be aware
                     flight_desc = "<span style='color:grey;'>_Likely Canceled/Error_</span>"
            else: # No price, no details, no error in quick_view (e.g. if entry was malformed or missing numeric_price)
                flight_desc = "_No data found_"

            current_price_latest_check_disp = "N/A"
            trend_val = " "
            if flight_date_str in tracked_dates_data:
                date_tracking_info = tracked_dates_data[flight_date_str]
                latest_snap = date_tracking_info.get("latest_check_snapshot", {})
                trend_val = get_price_trend_emoji(latest_snap.get("google_price_trend"))
                if latest_snap:
                    snap_error = latest_snap.get("error_if_any")
                    current_cheapest_flight_info = latest_snap.get("cheapest_flight_found")
                    if snap_error:
                        current_price_latest_check_disp = "<span style='color:orange;'>Error</span>"
                    elif current_cheapest_flight_info:
                        current_numeric_price = current_cheapest_flight_info.get("numeric_price")
                        current_price_latest_check_disp = format_price(current_numeric_price)
                    elif latest_snap.get("number_of_flights_found", 0) == 0: # Check this after error and price
                        current_price_latest_check_disp = "No flights"
                    # else: remains "N/A" if no error, no price, and num_flights not 0 (unusual case)

            md_section += f"| {flight_date_str}   | {day_short} | {overall_lowest_price_disp} | {current_price_latest_check_disp} | {flight_desc} | {airline} | {duration} | {stops_val} | {found_on_ist} | {trend_val} |\n"
    md_section += "\n"

    # --- Recently Observed Prices Tables ---
    if tracked_dates_data:
        for period_days, period_title_suffix in [(7, "Last 7 Days"), (14, "Last 14 Days")]:
            md_section += f"### Lowest Prices Observed in {period_title_suffix} (For This Route)\n"
            md_section += "_For each travel date, shows the cheapest *positive* price seen if an observation for that travel date occurred in this period._\n"
            
            recent_observations_table_content = ""
            table_header = "| Travel Date | Day | Lowest in Period | Current Price | Dep → Arr (Details) | Airline | Duration | Stops | Observed On (IST) |\n"
            table_separator = "|-------------|-----|------------------|---------------|-----------------------|---------|----------|-------|-------------------|\n"
            
            rows_for_period_table = 0
            sorted_tracked_dates_local = sorted(tracked_dates_data.keys())

            for flight_date_str_local in sorted_tracked_dates_local:
                date_specific_tracking_info = tracked_dates_data[flight_date_str_local]
                day_full_local = date_specific_tracking_info.get("day_of_week", "N/A")
                day_short_local = day_full_local[:3] if day_full_local != "N/A" else "N/A"
                
                observations_history = date_specific_tracking_info.get("hourly_observations_history", [])
                
                lowest_hist_price, flight_info_hist, obs_date_ist_str_hist = get_lowest_price_and_details_in_period(
                    observations_history, period_days, today_date
                )

                if lowest_hist_price is not None: # If a positive historical low was found in the period
                    rows_for_period_table += 1
                    lowest_hist_price_disp = format_price(lowest_hist_price)
                    flight_desc_hist, airline_hist, duration_hist, stops_val_hist = "N/A", "N/A", "N/A", "N/A"

                    if flight_info_hist:
                        airline_hist = flight_info_hist.get("name", "N/A")
                        dep_hist = extract_time(flight_info_hist.get("departure", "N/A"))
                        arr_hist = extract_time(flight_info_hist.get("arrival", "N/A"))
                        arr_ahead_hist = flight_info_hist.get("arrival_time_ahead", "")
                        flight_desc_hist = f"{dep_hist} → {arr_hist}{arr_ahead_hist if arr_ahead_hist else ''}"
                        duration_hist = flight_info_hist.get("duration", "N/A")
                        stops_val_hist = str(flight_info_hist.get("stops", "N/A"))
                    else: 
                        flight_desc_hist = "_Details N/A_"
                    
                    current_price_for_this_travel_date_disp = "N/A"
                    latest_snap_for_travel_date = date_specific_tracking_info.get("latest_check_snapshot", {})
                    if latest_snap_for_travel_date:
                        snap_error_hist = latest_snap_for_travel_date.get("error_if_any")
                        current_cheapest_info_hist = latest_snap_for_travel_date.get("cheapest_flight_found")
                        if snap_error_hist:
                             current_price_for_this_travel_date_disp = "<span style='color:orange;'>Error</span>"
                        elif current_cheapest_info_hist:
                            current_price_val = current_cheapest_info_hist.get("numeric_price")
                            current_price_for_this_travel_date_disp = format_price(current_price_val)
                        elif latest_snap_for_travel_date.get("number_of_flights_found", 0) == 0:
                             current_price_for_this_travel_date_disp = "No flights"
                        # else: remains "N/A"
                            
                    recent_observations_table_content += f"| {flight_date_str_local} | {day_short_local} | {lowest_hist_price_disp} | {current_price_for_this_travel_date_disp} | {flight_desc_hist} | {airline_hist} | {duration_hist} | {stops_val_hist} | {obs_date_ist_str_hist} |\n"

            if rows_for_period_table > 0:
                md_section += table_header + table_separator + recent_observations_table_content
            else:
                md_section += f"_No *positive* flight prices were observed for any travel date in the {period_title_suffix.lower()}._\n"
            md_section += "\n"
            
    return md_section

def generate_master_markdown(json_files, output_md_file):
    today = date.today() # Get today's date once
    generated_at_utc = datetime.now(timezone.utc)
    generated_at_ist_str = format_iso_timestamp_to_ist_string(generated_at_utc.isoformat())
    
    master_md_content = f"# Flight Price Summary ✈️\n\n"
    master_md_content += f"_{{This README is automatically updated. Last generated: {generated_at_ist_str}}}_\n\n"
    master_md_content += "This page shows the latest tracked flight prices for configured routes. Prices are for one adult, economy, one-way, in INR. All timestamps are in IST.\n\n"
    
    processed_any_valid_file = False
    sorted_json_files = sorted(json_files) # Sort files for consistent README output order

    for json_file_path in sorted_json_files:
        if os.path.exists(json_file_path):
            print(f"Processing {json_file_path} for Markdown report...")
            master_md_content += generate_route_markdown(json_file_path, today)
            master_md_content += "\n---\n" # Separator between routes
            processed_any_valid_file = True
        else:
            print(f"Warning: JSON file {json_file_path} not found. Skipping for Markdown report.")
            master_md_content += f"## Data for {os.path.basename(json_file_path)}\n\n_File not found during Markdown generation._\n\n---\n"
            
    if not processed_any_valid_file and json_files: # If files were specified but none were valid
        master_md_content += "\n_No valid data files were found or processed successfully from the provided list._\n"
    elif not json_files: # If no files were specified at all
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
        output_filename_arg = "README.md" # Default output filename
        print(f"Defaulting to {output_filename_arg} and discovering JSON files locally.")
        json_files_args = [f for f in os.listdir('.') if f.startswith("flight_tracker_") and f.endswith(".json")]

    if not json_files_args:
        print("No flight_tracker_*.json files found to process.")
        # Create an empty/informative README if no JSON files are found
        # but an output file is specified (e.g. README.md by default)
        # This prevents error if script is run in an empty repo for the first time.
        if output_filename_arg:
             generate_master_markdown([], output_filename_arg)
        sys.exit(0) # Exit gracefully

    print(f"Found JSON files for report: {sorted(json_files_args)}")
    print(f"Output Markdown to: {output_filename_arg}")
    if not generate_master_markdown(json_files_args, output_filename_arg):
        sys.exit(1) # Exit with error if generation failed