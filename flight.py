# flight.py
from fast_flights import FlightData, Passengers, Result, get_flights_from_filter, create_filter
from datetime import datetime, timedelta, date, timezone
import json
import time
import random
import os
import requests

# --- CONFIGURATION --- (Assuming this is the same)
ROUTES = [
    {"origin": "HYD", "destination": "DEL", "label": "HYD_to_DEL"},
    {"origin": "DEL", "destination": "HYD", "label": "DEL_to_HYD"},
    {"origin": "DEL", "destination": "BLR", "label": "DEL_to_BLR"}
]
NUM_ADULTS = 1
MIN_REQUEST_DELAY = 1.0
MAX_REQUEST_DELAY = 3.0
DAYS_INTO_FUTURE = 30
# --- END CONFIGURATION ---

# --- TELEGRAM CONFIGURATION --- (Assuming this is the same)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPOSITORY', 'your_username/your_repo')
# --- END TELEGRAM CONFIGURATION ---

# --- Helper functions (escape_markdown_v2, send_telegram_notification_for_new_lowest, 
# send_telegram_notification_for_price_drop_since_last_check, get_json_filename, 
# load_existing_data, save_data, fetch_single_date_flights) ---
# These functions can remain largely the same as your provided version.
# Ensure `fetch_single_date_flights` correctly returns the full result or error.

def escape_markdown_v2(text):
    if text is None: return ''
    s = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    res = []
    for char_val in s:
        if char_val in escape_chars: res.append('\\')
        res.append(char_val)
    return "".join(res)

def send_telegram_notification_for_new_lowest(origin, destination, flight_date_str, day_of_week,
                                           new_price, old_price, flight_details_dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID not configured. Skipping notification.")
        return
    
    esc_origin, esc_destination = escape_markdown_v2(origin), escape_markdown_v2(destination)
    esc_flight_date_str, esc_day_of_week = escape_markdown_v2(flight_date_str), escape_markdown_v2(day_of_week)
    esc_new_price = escape_markdown_v2(str(new_price))
    esc_old_price_text = 'N/A' if old_price == float('inf') else str(old_price)
    esc_old_price = escape_markdown_v2(esc_old_price_text)
    
    esc_dep_time = escape_markdown_v2(flight_details_dict.get("departure", "N/A"))
    esc_arr_time = escape_markdown_v2(flight_details_dict.get("arrival", "N/A"))
    esc_airline = escape_markdown_v2(flight_details_dict.get("name", "N/A"))
    esc_stops = escape_markdown_v2(str(flight_details_dict.get("stops", "N/A")))
    esc_duration = escape_markdown_v2(flight_details_dict.get("duration", "N/A"))
    
    message = (
        f"🎉 *New Overall Lowest Price Alert* 🎉\n\n"
        f"Route: *{esc_origin} ➔ {esc_destination}*\n"
        f"Travel Date: *{esc_flight_date_str}* {esc_day_of_week}\n"
        f"New Lowest Price: *₹{esc_new_price}*\n"
        f"Previously: ₹{esc_old_price}\n\n"
        f"*Flight Details:*\n"
        f"  Airline: {esc_airline}\n  Departure: {esc_dep_time}\n  Arrival: {esc_arr_time}\n"
        f"  Duration: {esc_duration}\n  Stops: {esc_stops}\n\n"
    )
    url_tg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url_tg_api, data=payload, timeout=10)
        response.raise_for_status()
        print(f"  Telegram (New Overall Lowest) sent for {flight_date_str}: {response.json().get('ok')}")
    except requests.exceptions.RequestException as e:
        print(f"  Error sending Telegram (New Overall Lowest) for {flight_date_str}: {e}")
        if hasattr(e, 'response') and e.response is not None: print(f"    TG API Error: {e.response.text}")
    except Exception as e: print(f"  Unexpected error sending Telegram (New Overall Lowest): {e}")


def send_telegram_notification_for_price_drop_since_last_check(origin, destination, flight_date_str, day_of_week,
                                                            current_snapshot_price, previous_snapshot_price, flight_details_dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bot token or chat ID not configured. Skipping notification.")
        return
    esc_origin, esc_destination = escape_markdown_v2(origin), escape_markdown_v2(destination)
    esc_flight_date_str, esc_day_of_week = escape_markdown_v2(flight_date_str), escape_markdown_v2(day_of_week)
    esc_current_price = escape_markdown_v2(str(current_snapshot_price))
    esc_previous_price = escape_markdown_v2(str(previous_snapshot_price))
    esc_dep_time = escape_markdown_v2(flight_details_dict.get("departure", "N/A"))
    esc_arr_time = escape_markdown_v2(flight_details_dict.get("arrival", "N/A"))
    esc_airline = escape_markdown_v2(flight_details_dict.get("name", "N/A"))
    esc_stops = escape_markdown_v2(str(flight_details_dict.get("stops", "N/A")))
    esc_duration = escape_markdown_v2(flight_details_dict.get("duration", "N/A"))
    message = (
        f"📉 *Price Drop Alert Since Last Check* 📉\n\n"
        f"Route: *{esc_origin} ➔ {esc_destination}*\n"
        f"Travel Date: *{esc_flight_date_str}* {esc_day_of_week}\n"
        f"Current Price: *₹{esc_current_price}*\n"
        f"Previously: ₹{esc_previous_price} in last check\n\n"
        f"*Current Flight Details:*\n"
        f"  Airline: {esc_airline}\n  Departure: {esc_dep_time}\n  Arrival: {esc_arr_time}\n"
        f"  Duration: {esc_duration}\n  Stops: {esc_stops}\n"
    )
    url_tg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url_tg_api, data=payload, timeout=10)
        response.raise_for_status()
        print(f"  Telegram (Drop Since Last Check) sent for {flight_date_str}: {response.json().get('ok')}")
    except requests.exceptions.RequestException as e:
        print(f"  Error sending Telegram (Drop Since Last Check) for {flight_date_str}: {e}")
        if hasattr(e, 'response') and e.response is not None: print(f"    TG API Error: {e.response.text}")
    except Exception as e: print(f"  Unexpected error sending Telegram (Drop Since Last Check): {e}")

def get_json_filename(route_label: str): return f"flight_tracker_{route_label}.json"

def load_existing_data(filepath: str):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f: data = json.load(f)
            if all(k in data for k in ["meta_info", "tracked_flight_dates", "lowest_price_quick_view"]): return data
            print(f"Warning: File {filepath} has unexpected structure. Initializing.")
        except Exception as e: print(f"Warning: Error loading/parsing {filepath}: {e}. Initializing.")
    return {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}

def save_data(filepath: str, data: dict, origin: str, destination: str):
    data["meta_info"]["origin"], data["meta_info"]["destination"] = origin, destination
    data["meta_info"]["script_last_successful_run_timestamp"] = datetime.now(timezone.utc).isoformat() # Use UTC for consistency
    try:
        with open(filepath, "w", encoding='utf-8') as f: json.dump(data, f, indent=4)
        print(f"Data successfully saved to {filepath}")
    except Exception as e: print(f"Error saving data to {filepath}: {e}")

def fetch_single_date_flights(target_date_obj: date, origin: str, dest: str, adults: int):
    date_str, day_of_week = target_date_obj.strftime("%Y-%m-%d"), target_date_obj.strftime("%A")
    print(f"Fetching flights for {origin}->{dest} on: {date_str} ({day_of_week})")
    try:
        flight_filter = create_filter(
            flight_data=[FlightData(date=date_str, from_airport=origin, to_airport=dest)],
            trip="one-way", seat="economy", passengers=Passengers(adults=adults)
        )
        # Assuming fast-flights returns Result object with a 'flights' list
        # and each flight object in that list has a 'delay' attribute.
        result: Result = get_flights_from_filter(flight_filter, currency="INR", mode="fallback")
        
        # MODIFICATION: Filter out cancelled flights from the result object
        valid_flights = []
        if result and result.flights:
            for flight in result.flights:
                delay_info = getattr(flight, 'delay', None) # Get the delay attribute
                # Check if delay_info is a string and contains "cancel" (case-insensitive)
                if isinstance(delay_info, str) and "cancel" in delay_info.lower():
                    print(f"  -> Discarding cancelled flight: {getattr(flight, 'name', 'Unknown Flight')} on {date_str}")
                    continue # Skip this flight
                valid_flights.append(flight)
        
        # Update the result object's flights list
        if result:
            result.flights = valid_flights # Now result.flights only contains non-cancelled flights

        print(f"  Found {len(result.flights if result else [])} non-cancelled flights. Trend: {result.current_price if result else 'N/A'}")
        return {"result_obj": result, "day_of_week": day_of_week, "error": None}
    except Exception as e:
        error_type = type(e).__name__
        print(f"  {error_type} for {origin}->{dest} on {date_str}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"{error_type}: {e}"}


def flight_to_dict(flight_obj): # fast-flights Flight object to dict
    if not flight_obj: return None
    return {
        "is_best": getattr(flight_obj, 'is_best', None),
        "name": getattr(flight_obj, 'name', None), # Usually airline name
        "departure": getattr(flight_obj, 'departure', None), # Expected string like "10:00 AM" or "10:00 AM on Mon, Jan 1"
        "arrival": getattr(flight_obj, 'arrival', None), # Expected string
        "arrival_time_ahead": getattr(flight_obj, 'arrival_time_ahead', None), # e.g. "+1 day"
        "duration": getattr(flight_obj, 'duration', None), # Expected string like "2h 30m"
        "stops": getattr(flight_obj, 'stops', None), # Expected int or string "Nonstop"
        "delay": getattr(flight_obj, 'delay', None), # Raw delay string (e.g., "On time", "Delayed 30 min", "Cancelled")
        "price": getattr(flight_obj, 'price', None) # Raw price string (e.g., "₹5,000")
    }

def convert_price_str_to_numeric(price_str):
    if not price_str: return None
    try:
        cleaned = ''.join(filter(str.isdigit, price_str.replace('₹', '').replace(',', '').split('.')[0]))
        if cleaned:
            price = float(cleaned)
            if price == 0.0: return None # Discard 0.0 prices as invalid for "lowest"
            return price
    except: pass
    return None

def get_cheapest_flight_from_result(result_obj: Result): # result_obj.flights are already filtered for cancellations
    if not result_obj or not result_obj.flights: return None, None # No valid flights
    cheapest_obj, min_price = None, float('inf')
    for flight in result_obj.flights: # Iterate through already filtered flights
        num_price = convert_price_str_to_numeric(getattr(flight, 'price', None))
        if num_price is not None and num_price < min_price: # num_price is already > 0 or None
            min_price, cheapest_obj = num_price, flight
    return (cheapest_obj, min_price) if cheapest_obj and min_price != float('inf') else (None, None)


def process_route_data(origin: str, destination: str, route_label: str):
    print(f"\n--- Processing Route: {origin} to {destination} ({route_label}) ---")
    json_filepath = get_json_filename(route_label)
    master_data = load_existing_data(json_filepath)
    start_date_obj = date.today()
    is_first_api_call = True

    for day_offset in range(DAYS_INTO_FUTURE):
        current_processing_date = start_date_obj + timedelta(days=day_offset)
        flight_date_str = current_processing_date.strftime("%Y-%m-%d")
        current_check_timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        previous_snapshot_price = None
        if flight_date_str in master_data["tracked_flight_dates"]:
            old_latest_snapshot = master_data["tracked_flight_dates"][flight_date_str].get("latest_check_snapshot")
            if old_latest_snapshot and old_latest_snapshot.get("cheapest_flight_found"):
                # Only consider positive previous prices for drop notification comparison
                prev_numeric = old_latest_snapshot["cheapest_flight_found"].get("numeric_price")
                if prev_numeric is not None and prev_numeric > 0:
                    previous_snapshot_price = prev_numeric


        if not is_first_api_call: time.sleep(random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY))
        is_first_api_call = False

        fetched = fetch_single_date_flights(current_processing_date, origin, destination, NUM_ADULTS)
        
        if flight_date_str not in master_data["tracked_flight_dates"]:
            master_data["tracked_flight_dates"][flight_date_str] = {
                "day_of_week": fetched["day_of_week"], "latest_check_snapshot": None,
                "lowest_price_ever_recorded": None, "hourly_observations_history": []
            }
        master_data["tracked_flight_dates"][flight_date_str]["day_of_week"] = fetched["day_of_week"]

        current_flight_obj, current_price = (None, None) # current_price is non-zero valid or None
        g_trend, num_valid_flights, err_msg = "unknown", 0, fetched["error"]

        # `fetched["result_obj"].flights` is already filtered for non-cancelled flights
        if fetched["result_obj"] and fetched["result_obj"].flights:
            current_flight_obj, current_price = get_cheapest_flight_from_result(fetched["result_obj"])
            g_trend = fetched["result_obj"].current_price
            num_valid_flights = len(fetched["result_obj"].flights) # Count of non-cancelled
        
        # For latest_snapshot, report what was found, including if all were cancelled (num_valid_flights would be 0)
        # The `current_flight_obj` and `current_price` here will be None if all were cancelled or no price > 0
        latest_snapshot_to_store = {
            "checked_at": current_check_timestamp_iso,
            "cheapest_flight_found": { 
                "numeric_price": current_price, # This is already non-zero or None
                "price_str": getattr(current_flight_obj, 'price', None) if current_flight_obj else None,
                "flight_details": flight_to_dict(current_flight_obj) # Will be None if no valid cheapest
            } if current_flight_obj else None, # Store None if no valid cheapest found
            "google_price_trend": g_trend, 
            "number_of_flights_found": num_valid_flights, # This is count of non-cancelled flights
            "error_if_any": err_msg
        }
        master_data["tracked_flight_dates"][flight_date_str]["latest_check_snapshot"] = latest_snapshot_to_store
        
        # Ensure hourly_observations_history is a list before appending
        if not isinstance(master_data["tracked_flight_dates"][flight_date_str].get("hourly_observations_history"), list):
            master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"] = []
        master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"].append(latest_snapshot_to_store)

        # --- Price Drop Since Last Check Notification Logic ---
        # Use current_price (which is >0 or None) for this notification
        if current_price is not None and \
           previous_snapshot_price is not None and \
           current_price < previous_snapshot_price: # Both are positive here
            
            print(f"  📉 Price drop since last check for {flight_date_str}: ₹{current_price} (was ₹{previous_snapshot_price})")
            send_telegram_notification_for_price_drop_since_last_check(
                origin, destination, flight_date_str, fetched["day_of_week"],
                current_price, previous_snapshot_price,            
                flight_to_dict(current_flight_obj) # current_flight_obj corresponds to current_price
            )

        # --- Overall Lowest Price Logic & Notification ---
        existing_lowest_record = master_data["tracked_flight_dates"][flight_date_str].get("lowest_price_ever_recorded")
        prev_overall_lowest_price = float('inf')
        if existing_lowest_record and existing_lowest_record.get("numeric_price") is not None:
            # Only consider positive previous overall lowest for comparison
             if existing_lowest_record["numeric_price"] > 0:
                 prev_overall_lowest_price = existing_lowest_record["numeric_price"]


        new_best_found_this_run = False
        if current_price is not None: # current_price is already non-zero valid or None
            if current_price < prev_overall_lowest_price:
                new_best_found_this_run = True
                print(f"  🎉 NEW OVERALL BEST for {flight_date_str}: ₹{current_price} (was ₹{prev_overall_lowest_price if prev_overall_lowest_price != float('inf') else 'N/A'})")
                new_record = {
                    "numeric_price": current_price, "price_str": getattr(current_flight_obj, 'price', None),
                    "flight_details": flight_to_dict(current_flight_obj),
                    "first_recorded_at": current_check_timestamp_iso, "last_confirmed_at": current_check_timestamp_iso
                }
                master_data["tracked_flight_dates"][flight_date_str]["lowest_price_ever_recorded"] = new_record
                master_data["lowest_price_quick_view"][flight_date_str] = {"day_of_week": fetched["day_of_week"], **new_record}
                send_telegram_notification_for_new_lowest(
                    origin, destination, flight_date_str, fetched["day_of_week"],
                    current_price, prev_overall_lowest_price, flight_to_dict(current_flight_obj)
                )
            elif current_price == prev_overall_lowest_price and existing_lowest_record: # current_price is > 0 here
                existing_lowest_record["last_confirmed_at"] = current_check_timestamp_iso
                if flight_date_str in master_data["lowest_price_quick_view"]:
                    master_data["lowest_price_quick_view"][flight_date_str]["last_confirmed_at"] = current_check_timestamp_iso
        
        # Update quick view with error/no flights if no valid current_price and no existing best
        if (err_msg or current_price is None) and not new_best_found_this_run:
            update_quick_view_with_status = False
            if flight_date_str not in master_data["lowest_price_quick_view"]:
                update_quick_view_with_status = True 
            elif master_data["lowest_price_quick_view"][flight_date_str].get("numeric_price") is None:
                # If existing quick view also has no valid price, update its error/status
                update_quick_view_with_status = True
            
            if update_quick_view_with_status:
                status_to_store = err_msg if err_msg else "No valid (non-cancelled, non-zero price) flights found this check"
                master_data["lowest_price_quick_view"][flight_date_str] = {
                    "day_of_week": fetched["day_of_week"], "numeric_price": None,
                    "price_str": None, "flight_details": None,
                    "first_recorded_at": None, "last_confirmed_at": None, "error": status_to_store
                }
        print(f"  Finished processing {flight_date_str} for {route_label}.")
    save_data(json_filepath, master_data, origin, destination)
    print(f"--- Finished Processing Route: {origin} to {destination} ({route_label}) ---")


def run_all_routes_job(): 
    print(f"========= Master Job Started: {datetime.now(timezone.utc).isoformat()} =========") 
    for route_info in ROUTES:
        process_route_data(route_info["origin"], route_info["destination"], route_info["label"])
    print(f"========= Master Job Ended: {datetime.now(timezone.utc).isoformat()} =========") 

if __name__ == "__main__": 
    print(f"Script started for flight data update run at {datetime.now(timezone.utc).isoformat()}.")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars not set. Notifications will be skipped.")
    else:
        masked_id = TELEGRAM_CHAT_ID[:4] + "..." if len(TELEGRAM_CHAT_ID) > 4 else TELEGRAM_CHAT_ID
        print(f"Telegram notifications enabled for chat ID: {masked_id}")
    run_all_routes_job()
    print("Script execution finished.")