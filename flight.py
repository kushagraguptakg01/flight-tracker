from fast_flights import FlightData, Passengers, Result, get_flights_from_filter, create_filter
from datetime import datetime, timedelta, date
import json
import time
import random
import os
import requests # For Telegram

# --- CONFIGURATION ---
ROUTES = [
    {"origin": "HYD", "destination": "DEL", "label": "HYD_to_DEL"},
    {"origin": "DEL", "destination": "HYD", "label": "DEL_to_HYD"},
    {"origin": "DEL", "destination": "BLR", "label": "DEL_to_BLR"}
]
NUM_ADULTS = 1
MIN_REQUEST_DELAY = 3.0
MAX_REQUEST_DELAY = 6.0
DAYS_INTO_FUTURE = 30
# RUN_INTERVAL_MINUTES = 10 # This constant is not used in flight.py, can be removed if not needed elsewhere
# --- END CONFIGURATION ---

# --- TELEGRAM CONFIGURATION (from environment variables) ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPOSITORY', 'your_username/your_repo') # For link
# --- END TELEGRAM CONFIGURATION ---

def escape_markdown_v2(text):
    if not isinstance(text, str):
        text = str(text) # Ensure text is a string
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Escape the escape character itself if it's not already escaped and is one of the special chars
    # This is tricky, simpler to just escape all special chars
    return "".join(['\\' + char if char in escape_chars else char for char in text])

def send_telegram_notification_for_new_lowest(origin, destination, flight_date_str, day_of_week,
                                           new_price, old_price, flight_details_dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID not configured. Skipping notification.")
        return

    # Ensure all dynamic parts are strings before escaping
    dep_time = escape_markdown_v2(str(flight_details_dict.get("departure_time", "N/A")))
    arr_time = escape_markdown_v2(str(flight_details_dict.get("arrival_time", "N/A")))
    airline = escape_markdown_v2(str(flight_details_dict.get("name", "N/A")))
    stops = escape_markdown_v2(str(flight_details_dict.get("stops", "N/A")))
    duration = escape_markdown_v2(str(flight_details_dict.get("duration_str", "N/A")))

    message = (
        f"🎉 *New Lowest Price Alert* 🎉\n\n"
        f"Route: *{escape_markdown_v2(origin)} ➔ {escape_markdown_v2(destination)}*\n"
        f"Travel Date: *{escape_markdown_v2(flight_date_str)}* ({escape_markdown_v2(day_of_week)})\n"
        f"New Lowest Price: *₹{escape_markdown_v2(str(new_price))}*\n"
        f"_(Previously: ₹{escape_markdown_v2(str(old_price) if old_price != float('inf') else 'N/A')})_\n\n"
        f"*Flight Details:*\n"
        f"  Airline: {airline}\n"
        f"  Departure: {dep_time}\n"
        f"  Arrival: {arr_time}\n"
        f"  Duration: {duration}\n"
        f"  Stops: {stops}\n\n"
        f"Check the [full summary on GitHub](https://github.com/{GITHUB_REPO_NAME}) for more details\\." # Escaped . for link
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print(f"  Telegram notification sent for {flight_date_str}: {response.json().get('ok')}")
    except requests.exceptions.RequestException as e:
        print(f"  Error sending Telegram notification for {flight_date_str}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"    Telegram API Response: {e.response.text}")
    except Exception as e:
        print(f"  An unexpected error occurred sending Telegram notification: {e}")


def get_json_filename(route_label: str):
    return f"flight_tracker_{route_label}.json"

def load_existing_data(filepath: str):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                if "meta_info" in data and "tracked_flight_dates" in data and "lowest_price_quick_view" in data:
                    return data
                else:
                    print(f"Warning: File {filepath} has an unexpected structure. Initializing for this route.")
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {filepath}. Initializing for this route.")
        except Exception as e:
            print(f"Warning: Error loading {filepath}: {e}. Initializing for this route.")
    return {
        "meta_info": { "script_last_successful_run_timestamp": None },
        "lowest_price_quick_view": {},
        "tracked_flight_dates": {}
    }

def save_data(filepath: str, data: dict, origin: str, destination: str):
    data["meta_info"]["origin"] = origin
    data["meta_info"]["destination"] = destination
    data["meta_info"]["script_last_successful_run_timestamp"] = datetime.now().isoformat()
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Data successfully saved to {filepath}")
    except Exception as e:
        print(f"Error saving data to {filepath}: {e}")

def fetch_single_date_flights(target_date_obj: date, origin: str, destination: str, adults: int):
    date_str = target_date_obj.strftime("%Y-%m-%d")
    day_of_week = target_date_obj.strftime("%A")
    print(f"Fetching flights for {origin}->{destination} on: {date_str} ({day_of_week})")
    try:
        flight_filter = create_filter(
            flight_data=[FlightData(date=date_str, from_airport=origin, to_airport=destination)],
            trip="one-way", seat="economy",
            passengers=Passengers(adults=adults)
        )
        result: Result = get_flights_from_filter(
            flight_filter,
            currency="INR",
            mode="fallback"
        )
        print(f"  Found {len(result.flights)} flights for {origin}->{destination}. Trend: {result.current_price}")
        return {"result_obj": result, "day_of_week": day_of_week, "error": None}
    except RuntimeError as e:
        print(f"  RuntimeError for {origin}->{destination} on {date_str}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"RuntimeError: {e}"}
    except Exception as e:
        print(f"  Unexpected Error for {origin}->{destination} on {date_str}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"Unexpected Error: {e}"}

def flight_to_dict(flight_obj):
    if not flight_obj: return None
    return {
        "is_best": getattr(flight_obj, 'is_best', None), "name": getattr(flight_obj, 'name', None),
        "departure_time": getattr(flight_obj, 'departure', None), "arrival_time": getattr(flight_obj, 'arrival', None),
        "arrival_time_ahead": getattr(flight_obj, 'arrival_time_ahead', None), "duration_str": getattr(flight_obj, 'duration', None),
        "stops": getattr(flight_obj, 'stops', None), "delay_info": getattr(flight_obj, 'delay', None),
        "price_str": getattr(flight_obj, 'price', None),
    }

def convert_price_str_to_numeric(price_str):
    if not price_str: return None
    try:
        cleaned_price_digits = ''.join(filter(str.isdigit, price_str.replace('₹', '').replace(',', '').split('.')[0]))
        if cleaned_price_digits: return float(cleaned_price_digits)
    except: pass
    return None

def get_cheapest_flight_from_result(result_obj: Result):
    if not result_obj or not result_obj.flights: return None, None
    cheapest_flight_obj, min_numeric_price = None, float('inf')
    for flight_obj in result_obj.flights:
        numeric_price = convert_price_str_to_numeric(getattr(flight_obj, 'price', None))
        if numeric_price is not None and numeric_price < min_numeric_price:
            min_numeric_price, cheapest_flight_obj = numeric_price, flight_obj
    return (cheapest_flight_obj, min_numeric_price) if cheapest_flight_obj else (None, None)

def process_route_data(origin: str, destination: str, route_label: str):
    print(f"\n--- Processing Route: {origin} to {destination} ({route_label}) ---")
    json_filepath = get_json_filename(route_label)
    master_data = load_existing_data(json_filepath) # Load existing data representing last known state

    start_date_obj = date.today()
    # end_date_obj = start_date_obj + timedelta(days=DAYS_INTO_FUTURE) # Original, a bit off for range
    # Corrected loop:
    
    is_first_api_call_in_route_processing = True

    for day_offset in range(DAYS_INTO_FUTURE): # Iterate 0 to DAYS_INTO_FUTURE-1
        current_processing_date = start_date_obj + timedelta(days=day_offset)
        flight_date_str = current_processing_date.strftime("%Y-%m-%d")
        current_check_timestamp_iso = datetime.now().isoformat()

        if not is_first_api_call_in_route_processing:
            delay_seconds = random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)
            # print(f"Waiting for {delay_seconds:.2f} seconds before next daily API call for {route_label}...") # Can be verbose
            time.sleep(delay_seconds)
        is_first_api_call_in_route_processing = False

        fetched_data_for_day = fetch_single_date_flights(
            current_processing_date, origin, destination, NUM_ADULTS
        )
        
        if flight_date_str not in master_data["tracked_flight_dates"]:
            master_data["tracked_flight_dates"][flight_date_str] = {
                "day_of_week": fetched_data_for_day["day_of_week"],
                "latest_check_snapshot": None, "lowest_price_ever_recorded": None,
                "hourly_observations_history": []
            }
        master_data["tracked_flight_dates"][flight_date_str]["day_of_week"] = fetched_data_for_day["day_of_week"]

        result_obj = fetched_data_for_day["result_obj"]
        error_msg = fetched_data_for_day["error"]
        
        cheapest_flight_this_check_obj, cheapest_numeric_price_this_check = (None, None)
        google_price_trend_this_check = "unknown"
        num_flights_this_check = 0

        if result_obj and result_obj.flights:
            cheapest_flight_this_check_obj, cheapest_numeric_price_this_check = get_cheapest_flight_from_result(result_obj)
            google_price_trend_this_check = result_obj.current_price
            num_flights_this_check = len(result_obj.flights)

        latest_snapshot = {
            "checked_at": current_check_timestamp_iso,
            "cheapest_flight_found": {
                "numeric_price": cheapest_numeric_price_this_check,
                "price_str": getattr(cheapest_flight_this_check_obj, 'price', None) if cheapest_flight_this_check_obj else None,
                "flight_details": flight_to_dict(cheapest_flight_this_check_obj)
            } if cheapest_flight_this_check_obj else None,
            "google_price_trend": google_price_trend_this_check,
            "number_of_flights_found": num_flights_this_check,
            "error_if_any": error_msg
        }
        master_data["tracked_flight_dates"][flight_date_str]["latest_check_snapshot"] = latest_snapshot
        master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"].append(latest_snapshot) # Simplified history

        if cheapest_numeric_price_this_check is not None: # Only proceed if a valid price was found in this check
            # Get the currently stored "lowest_price_ever_recorded" for this travel date
            existing_lowest_record = master_data["tracked_flight_dates"][flight_date_str].get("lowest_price_ever_recorded")
            
            prev_overall_lowest_price = float('inf')
            if existing_lowest_record and existing_lowest_record.get("numeric_price") is not None:
                prev_overall_lowest_price = existing_lowest_record["numeric_price"]

            if cheapest_numeric_price_this_check < prev_overall_lowest_price:
                print(f"  🎉 NEW OVERALL BEST PRICE for {flight_date_str}: ₹{cheapest_numeric_price_this_check} (was ₹{prev_overall_lowest_price if prev_overall_lowest_price != float('inf') else 'N/A'})")
                new_best_record = {
                    "numeric_price": cheapest_numeric_price_this_check,
                    "price_str": getattr(cheapest_flight_this_check_obj, 'price', None),
                    "flight_details": flight_to_dict(cheapest_flight_this_check_obj),
                    "first_recorded_at": current_check_timestamp_iso, # This check found this new best
                    "last_confirmed_at": current_check_timestamp_iso  # Also this check
                }
                master_data["tracked_flight_dates"][flight_date_str]["lowest_price_ever_recorded"] = new_best_record
                master_data["lowest_price_quick_view"][flight_date_str] = {
                    "day_of_week": master_data["tracked_flight_dates"][flight_date_str]["day_of_week"],
                    **new_best_record
                }
                send_telegram_notification_for_new_lowest(
                    origin, destination, flight_date_str,
                    master_data["tracked_flight_dates"][flight_date_str]["day_of_week"],
                    cheapest_numeric_price_this_check,
                    prev_overall_lowest_price,
                    flight_to_dict(cheapest_flight_this_check_obj)
                )
            elif existing_lowest_record and cheapest_numeric_price_this_check == prev_overall_lowest_price:
                # Price is the same as overall best, update last_confirmed_at
                master_data["tracked_flight_dates"][flight_date_str]["lowest_price_ever_recorded"]["last_confirmed_at"] = current_check_timestamp_iso
                if flight_date_str in master_data["lowest_price_quick_view"]:
                     master_data["lowest_price_quick_view"][flight_date_str]["last_confirmed_at"] = current_check_timestamp_iso
        
        elif error_msg and flight_date_str not in master_data["lowest_price_quick_view"]: # Only add error to quick_view if no prior data for this date
             master_data["lowest_price_quick_view"][flight_date_str] = {
                "day_of_week": master_data["tracked_flight_dates"][flight_date_str]["day_of_week"],
                "numeric_price": None, "price_str": None, "flight_details": None,
                "first_recorded_at": None, "last_confirmed_at": None, "error": error_msg
            }
        
        print(f"  Finished processing {flight_date_str} for {route_label}.")
        # current_processing_date += timedelta(days=1) # This line moved to loop iterator

    save_data(json_filepath, master_data, origin, destination)
    print(f"--- Finished Processing Route: {origin} to {destination} ({route_label}) ---")

def run_all_routes_job():
    print(f"========= Master Job Started: {datetime.now().isoformat()} =========")
    for route_info in ROUTES:
        process_route_data(
            origin=route_info["origin"],
            destination=route_info["destination"],
            route_label=route_info["label"]
        )
    print(f"========= Master Job Ended: {datetime.now().isoformat()} =========")

if __name__ == "__main__":
    print(f"Script started for flight data update run.") # Modified message
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables are not set. Notifications will be skipped.")
    else:
        # Mask part of the chat ID for privacy in logs
        masked_chat_id = TELEGRAM_CHAT_ID[:4] + "..." if len(TELEGRAM_CHAT_ID) > 4 else TELEGRAM_CHAT_ID
        print(f"Telegram notifications enabled for chat ID: {masked_chat_id}")
    run_all_routes_job()
    print("Script execution finished.") # Modified message