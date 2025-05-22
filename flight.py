# flight.py
from fast_flights import FlightData, Passengers, Result, get_flights_from_filter, create_filter
from datetime import datetime, timedelta, date as DDate, timezone # Renamed date to DDate to avoid conflict
import json
import time
import random
import os
import requests
import sys

# --- CONFIGURATION ---
ROUTES = [
    {"origin": "HYD", "destination": "DEL", "label": "HYD_to_DEL"},
    {"origin": "DEL", "destination": "HYD", "label": "DEL_to_HYD"},
    {"origin": "DEL", "destination": "BLR", "label": "DEL_to_BLR"}
]
NUM_ADULTS = 1
MIN_REQUEST_DELAY = 1.0
MAX_REQUEST_DELAY = 3.0
DAYS_INTO_FUTURE = 30 # Adjust this if your special dates are further out (e.g., for June 2025, set to ~180+ if today is Jan 2025)

# --- PRIMARY TELEGRAM CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPOSITORY', 'your_username/your_repo')

# --- SECONDARY/SPECIAL TELEGRAM CONFIGURATION ---
SECONDARY_TELEGRAM_BOT_TOKEN = os.environ.get('SECONDARY_TELEGRAM_BOT_TOKEN')
SECONDARY_TELEGRAM_CHAT_ID = os.environ.get('SECONDARY_TELEGRAM_CHAT_ID')

# --- SPECIAL NOTIFICATION CONFIGURATION ---
# Dates should be in YYYY-MM-DD format for easy comparison
SPECIAL_NOTIFICATIONS_CONFIG = [
    {
        "route_label": "DEL_to_HYD",
        "origin": "DEL",
        "destination": "HYD",
        "start_date": "2025-06-03",
        "end_date": "2025-06-03",
        "chat_id_override": SECONDARY_TELEGRAM_CHAT_ID,
        "bot_token_override": SECONDARY_TELEGRAM_BOT_TOKEN
    },
    {
        "route_label": "DEL_to_HYD",
        "origin": "DEL",
        "destination": "HYD",
        "start_date": "2025-05-21",
        "end_date": "2025-05-23",
        "chat_id_override": SECONDARY_TELEGRAM_CHAT_ID,
        "bot_token_override": SECONDARY_TELEGRAM_BOT_TOKEN
    },
    {
        "route_label": "DEL_to_BLR",
        "origin": "DEL",
        "destination": "BLR",
        "start_date": "2025-06-09",
        "end_date": "2025-06-10",
        "chat_id_override": SECONDARY_TELEGRAM_CHAT_ID,
        "bot_token_override": SECONDARY_TELEGRAM_BOT_TOKEN
    }
]
# --- END CONFIGURATION ---

def escape_markdown_v2(text):
    if text is None: return ''
    s = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    res = []
    for char_val in s:
        if char_val in escape_chars: res.append('\\')
        res.append(char_val)
    return "".join(res)

def _send_telegram_message(bot_token, chat_id, message_text, subject_for_log):
    """Helper function to send a Telegram message."""
    if not bot_token or not chat_id:
        print(f"Telegram bot token or chat ID missing for {subject_for_log}. Skipping notification.")
        return False
    
    masked_chat_id_log = str(chat_id)[:4] + "..." if chat_id and len(str(chat_id)) > 4 else str(chat_id)
    url_tg_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message_text, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url_tg_api, data=payload, timeout=10)
        response.raise_for_status()
        print(f"  Telegram ({subject_for_log}) sent to chat ID {masked_chat_id_log}: {response.json().get('ok')}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  Error sending Telegram ({subject_for_log}) to chat ID {masked_chat_id_log}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"    TG API Error Status: {e.response.status_code}")
            try:
                print(f"    TG API Error Response: {e.response.json()}") # Or e.response.text if JSON parsing fails
            except ValueError:
                print(f"    TG API Error Response (not JSON): {e.response.text}")
        else:
            print(f"    Error does not have a response object or response is None.")
        return False
    except Exception as e:
        print(f"  Unexpected error sending Telegram ({subject_for_log}) to {masked_chat_id_log}: {e}")
        return False

def send_telegram_notification_for_new_lowest(
    origin, destination, flight_date_str, day_of_week,
    new_price, old_price, flight_details_dict,
    bot_token_override=None, chat_id_override=None):

    bot_token_to_use = bot_token_override if bot_token_override else TELEGRAM_BOT_TOKEN
    chat_id_to_use = chat_id_override if chat_id_override else TELEGRAM_CHAT_ID
    
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
    # if GITHUB_REPO_NAME and GITHUB_REPO_NAME != 'your_username/your_repo':
    #      message += f"View summary: https://github.com/{GITHUB_REPO_NAME}\n"

    log_subject = f"New Overall Lowest ({origin}->{destination} on {flight_date_str})"
    _send_telegram_message(bot_token_to_use, chat_id_to_use, message, log_subject)


def send_telegram_notification_for_price_drop_since_last_check(
    origin, destination, flight_date_str, day_of_week,
    current_snapshot_price, previous_snapshot_price, flight_details_dict,
    bot_token_override=None, chat_id_override=None):

    bot_token_to_use = bot_token_override if bot_token_override else TELEGRAM_BOT_TOKEN
    chat_id_to_use = chat_id_override if chat_id_override else TELEGRAM_CHAT_ID

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
    # if GITHUB_REPO_NAME and GITHUB_REPO_NAME != 'your_username/your_repo':
    #      message += f"View summary: https://github.com/{GITHUB_REPO_NAME}\n"

    log_subject = f"Price Drop ({origin}->{destination} on {flight_date_str})"
    _send_telegram_message(bot_token_to_use, chat_id_to_use, message, log_subject)

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

def fetch_single_date_flights(target_date_obj: DDate, origin: str, dest: str, adults: int):
    date_str, day_of_week = target_date_obj.strftime("%Y-%m-%d"), target_date_obj.strftime("%A")
    print(f"Fetching flights for {origin}->{dest} on: {date_str} ({day_of_week})")
    try:
        flight_filter = create_filter(
            flight_data=[FlightData(date=date_str, from_airport=origin, to_airport=dest)],
            trip="one-way", seat="economy", passengers=Passengers(adults=adults)
        )
        result: Result = get_flights_from_filter(flight_filter, currency="INR", mode="fallback")
        
        valid_flights = []
        if result and result.flights:
            for flight in result.flights:
                is_cancelled = False
                cancellation_reason = [] # Store reasons for cancellation

                # Hypothetical check 1: based on a status attribute
                flight_status = getattr(flight, 'status', None) # or 'state', 'flight_status' etc.
                if isinstance(flight_status, str) and flight_status.lower() in ['cancelled', 'canceled', 'revoked', 'x', 'cnl']:
                    is_cancelled = True
                    cancellation_reason.append(f"status: '{flight_status}'")
                
                # Hypothetical check 2: based on a boolean attribute
                if not is_cancelled and hasattr(flight, 'is_cancelled') and getattr(flight, 'is_cancelled') is True:
                    is_cancelled = True
                    cancellation_reason.append("is_cancelled: True")

                # Original check (fallback)
                delay_info = getattr(flight, 'delay', None) # Get it once
                if not is_cancelled and isinstance(delay_info, str) and "cancel" in delay_info.lower():
                    is_cancelled = True
                    cancellation_reason.append(f"delay_info: '{delay_info}'")
                
                if is_cancelled:
                    reason_str = ", ".join(cancellation_reason)
                    print(f"  -> Discarding cancelled flight: {getattr(flight, 'name', 'Unknown Flight')} on {date_str} (Reason: {reason_str})")
                    continue
                valid_flights.append(flight)
        
        if result:
            result.flights = valid_flights

        print(f"  Found {len(valid_flights if result else [])} non-cancelled flights. Trend: {result.current_price if result else 'N/A'}")
        return {"result_obj": result, "day_of_week": day_of_week, "error": None}
    except Exception as e:
        error_type = type(e).__name__
        print(f"  {error_type} for {origin}->{dest} on {date_str}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"{error_type}: {e}"}


def flight_to_dict(flight_obj):
    if not flight_obj: return None

    # Helper to try multiple attribute names
    def get_attr_fallback(obj, primary_name, secondary_name=None):
        val = getattr(obj, primary_name, None)
        if val is None and secondary_name:
            val = getattr(obj, secondary_name, None)
        return val

    details = {
        "is_best": get_attr_fallback(flight_obj, 'is_best'),
        "name": get_attr_fallback(flight_obj, 'name', 'airline_name'), # Try 'name', then 'airline_name'
        "departure": get_attr_fallback(flight_obj, 'departure', 'dep_time'),
        "arrival": get_attr_fallback(flight_obj, 'arrival', 'arr_time'),
        "arrival_time_ahead": get_attr_fallback(flight_obj, 'arrival_time_ahead'), # Assuming this one is usually consistent
        "duration": get_attr_fallback(flight_obj, 'duration', 'total_duration'),
        "stops": get_attr_fallback(flight_obj, 'stops', 'num_stops'),
        "delay": get_attr_fallback(flight_obj, 'delay'), # Assuming this one is usually consistent
        "price": get_attr_fallback(flight_obj, 'price') # Assuming this one is usually consistent
    }

    # Convert stops to int if it's a string digit, otherwise keep as is (could be None or text like 'Non-stop')
    if isinstance(details["stops"], str) and details["stops"].isdigit():
        details["stops"] = int(details["stops"])
    elif details["stops"] is None and get_attr_fallback(flight_obj, 'stop_count') is not None: # Third fallback for stops
        stop_count_val = get_attr_fallback(flight_obj, 'stop_count')
        if isinstance(stop_count_val, str) and stop_count_val.isdigit():
             details["stops"] = int(stop_count_val)
        elif isinstance(stop_count_val, int): # If it's already an int
            details["stops"] = stop_count_val
        # If it's "Non-stop" or other text, it might remain None or its text value if primary/secondary picked it up.
        # This part specifically handles stop_count if primary/secondary 'stops'/'num_stops' were None.


    # Current diagnostic logging (keep it for now, might be removed in a later step)
    essential_keys = ["name", "departure", "arrival", "duration", "stops"]
    missing_essentials = [key for key in essential_keys if details[key] is None]
    if missing_essentials:
        original_price_str = details.get('price', 'N/A')
        flight_name_for_log = details.get('name', 'Unknown Airline') # Use the potentially resolved name
        print(f"  DEBUG flight_to_dict: Flight '{flight_name_for_log}' (Price: {original_price_str}) is missing essential details: {missing_essentials}. Flight object type: {type(flight_obj)}")
            
    return details

def convert_price_str_to_numeric(price_str):
    if not price_str: return None
    try:
        cleaned = ''.join(filter(str.isdigit, price_str.replace('₹', '').replace(',', '').split('.')[0]))
        if cleaned:
            price = float(cleaned)
            if price == 0.0:
                print(f"Warning: Price string '{price_str}' resulted in 0.0, treating as no valid price.")
                return None
            return price
    except: pass
    return None

def get_cheapest_flight_from_result(result_obj: Result):
    if not result_obj or not result_obj.flights: return None, None
    cheapest_obj, min_price = None, float('inf')
    for flight in result_obj.flights:
        num_price = convert_price_str_to_numeric(getattr(flight, 'price', None))
        if num_price is not None and num_price < min_price:
            min_price, cheapest_obj = num_price, flight
    
    return (cheapest_obj, min_price) if cheapest_obj and min_price != float('inf') else (None, None)

def get_special_notification_params(route_label_current, flight_date_str_current):
    try:
        current_date_obj = DDate.fromisoformat(flight_date_str_current)
    except ValueError:
        print(f"Warning: Invalid current_date_str '{flight_date_str_current}' in get_special_notification_params.")
        return None, None

    for config in SPECIAL_NOTIFICATIONS_CONFIG:
        if config["route_label"] == route_label_current:
            try:
                start_date_obj = DDate.fromisoformat(config["start_date"])
                end_date_obj = DDate.fromisoformat(config["end_date"])
                if start_date_obj <= current_date_obj <= end_date_obj:
                    token_override = config.get("bot_token_override")
                    chat_override = config.get("chat_id_override")
                    # Only return overrides if both are present and non-empty
                    if token_override and chat_override:
                        return token_override, chat_override
                    else:
                        print(f"Warning: Incomplete special notification setup for route '{route_label_current}' on {flight_date_str_current}. Bot token or chat ID (or both) is missing in SPECIAL_NOTIFICATIONS_CONFIG. Notifications for this specific date/route will use default Telegram settings if available. Please check your environment variables or SPECIAL_NOTIFICATIONS_CONFIG entry.")
                        return None, None # Fallback to default if specific overrides are not fully set
            except ValueError:
                print(f"Warning: Invalid date format in SPECIAL_NOTIFICATIONS_CONFIG for route {route_label_current} ('{config['start_date']}' or '{config['end_date']}'). Skipping this config entry.")
                continue
    return None, None


def process_route_data(origin: str, destination: str, route_label: str):
    print(f"\n--- Processing Route: {origin} to {destination} ({route_label}) ---")
    json_filepath = get_json_filename(route_label)
    master_data = load_existing_data(json_filepath)
    start_date_obj = DDate.today()
    is_first_api_call = True

    for day_offset in range(DAYS_INTO_FUTURE):
        current_processing_date = start_date_obj + timedelta(days=day_offset)
        flight_date_str = current_processing_date.strftime("%Y-%m-%d")
        current_check_timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        special_bot_token, special_chat_id = get_special_notification_params(route_label, flight_date_str)
        if special_bot_token and special_chat_id:
            print(f"  Special notification config active for {route_label} on {flight_date_str} to chat {str(special_chat_id)[:4]}...")

        previous_snapshot_price = None
        if flight_date_str in master_data["tracked_flight_dates"]:
            old_latest_snapshot = master_data["tracked_flight_dates"][flight_date_str].get("latest_check_snapshot")
            if old_latest_snapshot and old_latest_snapshot.get("cheapest_flight_found"):
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

        current_flight_obj, current_price = (None, None)
        g_trend, num_valid_flights, err_msg = "unknown", 0, fetched["error"]

        if fetched["result_obj"] and fetched["result_obj"].flights:
            current_flight_obj, current_price = get_cheapest_flight_from_result(fetched["result_obj"])
            g_trend = fetched["result_obj"].current_price
            num_valid_flights = len(fetched["result_obj"].flights)
        
        latest_snapshot_to_store = {
            "checked_at": current_check_timestamp_iso,
            "cheapest_flight_found": { 
                "numeric_price": current_price,
                "price_str": getattr(current_flight_obj, 'price', None) if current_flight_obj else None,
                "flight_details": flight_to_dict(current_flight_obj)
            } if current_flight_obj else None,
            "google_price_trend": g_trend, 
            "number_of_flights_found": num_valid_flights,
            "error_if_any": err_msg
        }
        master_data["tracked_flight_dates"][flight_date_str]["latest_check_snapshot"] = latest_snapshot_to_store
        
        if not isinstance(master_data["tracked_flight_dates"][flight_date_str].get("hourly_observations_history"), list):
            master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"] = []
        master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"].append(latest_snapshot_to_store)

        if current_price is not None and \
           previous_snapshot_price is not None and \
           current_price < previous_snapshot_price:
            
            print(f"  📉 Price drop since last check for {flight_date_str}: ₹{current_price} (was ₹{previous_snapshot_price})")
            send_telegram_notification_for_price_drop_since_last_check(
                origin, destination, flight_date_str, fetched["day_of_week"],
                current_price, previous_snapshot_price,            
                flight_to_dict(current_flight_obj),
                bot_token_override=special_bot_token,
                chat_id_override=special_chat_id
            )

        existing_lowest_record = master_data["tracked_flight_dates"][flight_date_str].get("lowest_price_ever_recorded")
        prev_overall_lowest_price = float('inf')
        if existing_lowest_record and existing_lowest_record.get("numeric_price") is not None:
             if existing_lowest_record["numeric_price"] > 0:
                 prev_overall_lowest_price = existing_lowest_record["numeric_price"]

        new_best_found_this_run = False
        if current_price is not None:
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
                    current_price, prev_overall_lowest_price, flight_to_dict(current_flight_obj),
                    bot_token_override=special_bot_token,
                    chat_id_override=special_chat_id
                )
            elif current_price == prev_overall_lowest_price and existing_lowest_record:
                existing_lowest_record["last_confirmed_at"] = current_check_timestamp_iso
                if flight_date_str in master_data["lowest_price_quick_view"]:
                    master_data["lowest_price_quick_view"][flight_date_str]["last_confirmed_at"] = current_check_timestamp_iso
        
        if (err_msg or current_price is None) and not new_best_found_this_run:
            update_quick_view_with_status = False
            if flight_date_str not in master_data["lowest_price_quick_view"]:
                update_quick_view_with_status = True 
            elif master_data["lowest_price_quick_view"][flight_date_str].get("numeric_price") is None:
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
        print("Warning: PRIMARY TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars not set. Default notifications will be skipped.")
    else:
        masked_id = TELEGRAM_CHAT_ID[:4] + "..." if TELEGRAM_CHAT_ID and len(TELEGRAM_CHAT_ID) > 4 else TELEGRAM_CHAT_ID
        print(f"Primary Telegram notifications enabled for chat ID: {masked_id}")

    if not SECONDARY_TELEGRAM_BOT_TOKEN or not SECONDARY_TELEGRAM_CHAT_ID:
        print("Warning: SECONDARY_TELEGRAM_BOT_TOKEN or SECONDARY_TELEGRAM_CHAT_ID env vars not set. Special notifications will be skipped if configured to use them, or if the special config itself is missing these values.")
    else:
        masked_secondary_id = SECONDARY_TELEGRAM_CHAT_ID[:4] + "..." if SECONDARY_TELEGRAM_CHAT_ID and len(SECONDARY_TELEGRAM_CHAT_ID) > 4 else SECONDARY_TELEGRAM_CHAT_ID
        print(f"Secondary/Special Telegram notifications enabled for chat ID: {masked_secondary_id}")
    
    # Example: Check if DAYS_INTO_FUTURE is sufficient for special configs
    today = DDate.today()
    max_special_date = None
    for sconf in SPECIAL_NOTIFICATIONS_CONFIG:
        try:
            s_end_date = DDate.fromisoformat(sconf["end_date"])
            if max_special_date is None or s_end_date > max_special_date:
                max_special_date = s_end_date
        except ValueError:
            pass # Already warned by get_special_notification_params if format is bad
    
    if max_special_date:
        days_needed = (max_special_date - today).days + 1 # +1 to include the end date
        if DAYS_INTO_FUTURE < days_needed:
            print(f"ERROR: DAYS_INTO_FUTURE ({DAYS_INTO_FUTURE}) is insufficient for special notifications up to {max_special_date} (requires {days_needed} days).")
            print("Please increase DAYS_INTO_FUTURE in the script's configuration or adjust your SPECIAL_NOTIFICATIONS_CONFIG.")
            print("Exiting script to prevent missing special notifications.")
            sys.exit(1) # Exit the script

    run_all_routes_job()
    print("Script execution finished.")