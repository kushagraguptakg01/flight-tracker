# flight.py
from fast_flights import FlightData, Passengers, Result, get_flights_from_filter, create_filter
from datetime import datetime, timedelta, date, timezone
import json
import time
import random
import os
import requests

# --- CONFIGURATION ---
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

# --- TELEGRAM CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPOSITORY', 'your_username/your_repo')
# --- END TELEGRAM CONFIGURATION ---

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
    # ... (escaping and message construction as in the previous correct version) ...
    esc_origin, esc_destination = escape_markdown_v2(origin), escape_markdown_v2(destination)
    esc_flight_date_str, esc_day_of_week = escape_markdown_v2(flight_date_str), escape_markdown_v2(day_of_week)
    esc_new_price = escape_markdown_v2(str(new_price))
    esc_old_price_text = 'N/A' if old_price == float('inf') else str(old_price)
    esc_old_price = escape_markdown_v2(esc_old_price_text)
    esc_dep_time = escape_markdown_v2(str(flight_details_dict.get("departure_time", "N/A")))
    esc_arr_time = escape_markdown_v2(str(flight_details_dict.get("arrival_time", "N/A")))
    esc_airline = escape_markdown_v2(str(flight_details_dict.get("name", "N/A")))
    esc_stops = escape_markdown_v2(str(flight_details_dict.get("stops", "N/A")))
    esc_duration = escape_markdown_v2(str(flight_details_dict.get("duration_str", "N/A")))
    github_link_url = f"https://github.com/{GITHUB_REPO_NAME}"
    link_display_text = "full summary on GitHub"
    message = (
        f"🎉 *New Lowest Price Alert* 🎉\n\n"
        f"Route: *{esc_origin} ➔ {esc_destination}*\n"
        f"Travel Date: *{esc_flight_date_str}* {esc_day_of_week}\n"
        f"New Lowest Price: *₹{esc_new_price}*\n"
        f"Previously: ₹{esc_old_price}\n\n"
        f"*Flight Details:*\n"
        f"  Airline: {esc_airline}\n  Departure: {esc_dep_time}\n  Arrival: {esc_arr_time}\n"
        f"  Duration: {esc_duration}\n  Stops: {esc_stops}\n\n"
        # f"Check the [{link_display_text}]({github_link_url}) for more details\\."
    )
    url_tg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url_tg_api, data=payload, timeout=10)
        response.raise_for_status()
        print(f"  Telegram notification sent for {flight_date_str}: {response.json().get('ok')}")
    except requests.exceptions.RequestException as e:
        print(f"  Error sending Telegram for {flight_date_str}: {e}")
        if hasattr(e, 'response') and e.response is not None: print(f"    TG API Error: {e.response.text}")
    except Exception as e: print(f"  Unexpected error sending Telegram: {e}")


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
    data["meta_info"]["script_last_successful_run_timestamp"] = datetime.now(timezone.utc).isoformat()
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
        result: Result = get_flights_from_filter(flight_filter, currency="INR", mode="fallback")
        print(f"  Found {len(result.flights)} flights. Trend: {result.current_price}")
        return {"result_obj": result, "day_of_week": day_of_week, "error": None}
    except Exception as e:
        error_type = type(e).__name__
        print(f"  {error_type} for {origin}->{dest} on {date_str}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"{error_type}: {e}"}

def flight_to_dict(flight_obj):
    if not flight_obj: return None
    return {k: getattr(flight_obj, k, None) for k in [
        "is_best", "name", "departure", "arrival", "arrival_time_ahead", 
        "duration", "stops", "delay", "price"
    ]}

def convert_price_str_to_numeric(price_str):
    if not price_str: return None
    try:
        cleaned = ''.join(filter(str.isdigit, price_str.replace('₹', '').replace(',', '').split('.')[0]))
        if cleaned:
            price = float(cleaned)
            # MODIFICATION: Ignore 0.0 as a valid price here
            if price == 0.0:
                return None 
            return price
    except: pass
    return None

def get_cheapest_flight_from_result(result_obj: Result):
    if not result_obj or not result_obj.flights: return None, None
    cheapest_obj, min_price = None, float('inf')
    for flight in result_obj.flights:
        num_price = convert_price_str_to_numeric(getattr(flight, 'price', None))
        # num_price will be None if it was 0.0 due to the change in convert_price_str_to_numeric
        if num_price is not None and num_price < min_price:
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

        if not is_first_api_call: time.sleep(random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY))
        is_first_api_call = False

        fetched = fetch_single_date_flights(current_processing_date, origin, destination, NUM_ADULTS)
        
        if flight_date_str not in master_data["tracked_flight_dates"]:
            master_data["tracked_flight_dates"][flight_date_str] = {
                "day_of_week": fetched["day_of_week"], "latest_check_snapshot": None,
                "lowest_price_ever_recorded": None, "hourly_observations_history": []
            }
        master_data["tracked_flight_dates"][flight_date_str]["day_of_week"] = fetched["day_of_week"]

        # current_price will be None if cheapest is 0.0 or no flights/error
        current_flight_obj, current_price = (None, None) 
        g_trend, num_flights, err_msg = "unknown", 0, fetched["error"]

        if fetched["result_obj"] and fetched["result_obj"].flights:
            # get_cheapest_flight_from_result now filters out 0.0 prices
            current_flight_obj, current_price = get_cheapest_flight_from_result(fetched["result_obj"])
            g_trend = fetched["result_obj"].current_price
            num_flights = len(fetched["result_obj"].flights)
        
        # For latest_snapshot, we record what was found, even if it was a 0 price flight object before filtering
        # So, we get the raw cheapest, which might include 0.0
        raw_cheapest_flight_obj_this_check, raw_cheapest_numeric_price_this_check = (None, None)
        if fetched["result_obj"] and fetched["result_obj"].flights:
            # Temporarily allow 0.0 for snapshot reporting, but not for "best price" logic
            temp_cheapest_flight, temp_cheapest_price = None, float('inf')
            for flight_obj_snap in fetched["result_obj"].flights:
                snap_price_str = getattr(flight_obj_snap, 'price', None)
                snap_numeric_price = None
                if snap_price_str is not None:
                    try:
                        cleaned_digits = ''.join(filter(str.isdigit, snap_price_str.replace('₹', '').replace(',', '').split('.')[0]))
                        if cleaned_digits: snap_numeric_price = float(cleaned_digits)
                    except: pass
                
                if snap_numeric_price is not None and snap_numeric_price < temp_cheapest_price:
                    temp_cheapest_price = snap_numeric_price
                    temp_cheapest_flight = flight_obj_snap
            raw_cheapest_flight_obj_this_check = temp_cheapest_flight
            raw_cheapest_numeric_price_this_check = temp_cheapest_price if temp_cheapest_price != float('inf') else None


        latest_snapshot = {
            "checked_at": current_check_timestamp_iso,
            "cheapest_flight_found": { # This snapshot records the actual cheapest, even if 0
                "numeric_price": raw_cheapest_numeric_price_this_check,
                "price_str": getattr(raw_cheapest_flight_obj_this_check, 'price', None) if raw_cheapest_flight_obj_this_check else None,
                "flight_details": flight_to_dict(raw_cheapest_flight_obj_this_check)
            } if raw_cheapest_flight_obj_this_check else None,
            "google_price_trend": g_trend, "number_of_flights_found": num_flights, "error_if_any": err_msg
        }
        master_data["tracked_flight_dates"][flight_date_str]["latest_check_snapshot"] = latest_snapshot
        if not isinstance(master_data["tracked_flight_dates"][flight_date_str].get("hourly_observations_history"), list):
            master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"] = []
        master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"].append(latest_snapshot)

        # --- Lowest Price Logic & Notification (uses `current_price` which excludes 0.0) ---
        existing_lowest_record = master_data["tracked_flight_dates"][flight_date_str].get("lowest_price_ever_recorded")
        prev_overall_lowest_price = float('inf')
        if existing_lowest_record and existing_lowest_record.get("numeric_price") is not None:
            # Ensure previous lowest is not 0.0 for comparison basis, unless it's the only thing recorded
            if existing_lowest_record["numeric_price"] > 0:
                 prev_overall_lowest_price = existing_lowest_record["numeric_price"]
            # If existing_lowest_record["numeric_price"] is 0.0, prev_overall_lowest_price remains inf, so any new valid price will be lower.

        new_best_found_this_run = False
        if current_price is not None: # current_price is already non-zero or None
            if current_price < prev_overall_lowest_price:
                new_best_found_this_run = True
                # ... (rest of the new best price and notification logic - IDENTICAL to previous correct version)
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
            elif current_price == prev_overall_lowest_price and existing_lowest_record and current_price > 0: # Only update confirmed if valid price
                existing_lowest_record["last_confirmed_at"] = current_check_timestamp_iso
                if flight_date_str in master_data["lowest_price_quick_view"]:
                    master_data["lowest_price_quick_view"][flight_date_str]["last_confirmed_at"] = current_check_timestamp_iso
        
        # Update quick_view if there's an error OR (no valid flight was found AND no new best was recorded this run)
        # This logic ensures quick_view reflects errors or "no flights" only if there isn't already a valid best price.
        if err_msg or (current_price is None and not new_best_found_this_run):
            update_quick_view_with_status = False
            if flight_date_str not in master_data["lowest_price_quick_view"]:
                update_quick_view_with_status = True # Date is new to quick_view
            else:
                # If existing quick_view entry is already an error or has no price, it's okay to update
                qv_entry = master_data["lowest_price_quick_view"][flight_date_str]
                if qv_entry.get("numeric_price") is None: # existing is error or no data
                    update_quick_view_with_status = True
            
            if update_quick_view_with_status:
                status_to_store = err_msg if err_msg else "No valid (non-zero) flights found this check"
                master_data["lowest_price_quick_view"][flight_date_str] = {
                    "day_of_week": fetched["day_of_week"], "numeric_price": None,
                    "price_str": None, "flight_details": None,
                    "first_recorded_at": None, "last_confirmed_at": None, "error": status_to_store
                }

        print(f"  Finished processing {flight_date_str} for {route_label}.")
    save_data(json_filepath, master_data, origin, destination)
    print(f"--- Finished Processing Route: {origin} to {destination} ({route_label}) ---")


def run_all_routes_job(): # (Identical)
    print(f"========= Master Job Started: {datetime.now(timezone.utc).isoformat()} =========") 
    for route_info in ROUTES:
        process_route_data(route_info["origin"], route_info["destination"], route_info["label"])
    print(f"========= Master Job Ended: {datetime.now(timezone.utc).isoformat()} =========") 

if __name__ == "__main__": # (Identical)
    print(f"Script started for flight data update run.")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars not set. Notifications will be skipped.")
    else:
        masked_id = TELEGRAM_CHAT_ID[:4] + "..." if len(TELEGRAM_CHAT_ID) > 4 else TELEGRAM_CHAT_ID
        print(f"Telegram notifications enabled for chat ID: {masked_id}")
    run_all_routes_job()
    print("Script execution finished.")