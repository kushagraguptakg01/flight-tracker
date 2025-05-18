from fast_flights import FlightData, Passengers, Result, get_flights_from_filter, create_filter
from datetime import datetime, timedelta, date
import json
import time
import random
import os

# --- CONFIGURATION ---
# Define a list of routes to track
ROUTES = [
    {"origin": "HYD", "destination": "DEL", "label": "HYD_to_DEL"},
    {"origin": "DEL", "destination": "HYD", "label": "DEL_to_HYD"}
]

NUM_ADULTS = 1
MIN_REQUEST_DELAY = 3.0  # Min seconds BETWEEN DAILY API requests within a single job run for a route
MAX_REQUEST_DELAY = 6.0  # Max seconds BETWEEN DAILY API requests within a single job run for a route
DAYS_INTO_FUTURE = 30
RUN_INTERVAL_MINUTES = 10 # How often the main job (processing all routes) should run
# --- END CONFIGURATION ---

def get_json_filename(route_label: str):
    """Generates the JSON filename for a given route."""
    return f"flight_tracker_{route_label}.json" # Files will be in the same directory as the script

def load_existing_data(filepath: str):
    """Loads existing JSON data from the file, or returns a default structure."""
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
    
    # Return default structure if file doesn't exist or loading failed
    # Origin/Destination in meta_info will be set dynamically when saving
    return {
        "meta_info": { # To be populated with specific route info later
            "script_last_successful_run_timestamp": None
        },
        "lowest_price_quick_view": {},
        "tracked_flight_dates": {}
    }

def save_data(filepath: str, data: dict, origin: str, destination: str):
    """Saves the data dictionary to the JSON file, adding route-specific meta_info."""
    data["meta_info"]["origin"] = origin # Add/update route specific origin
    data["meta_info"]["destination"] = destination # Add/update route specific destination
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
        # Create the filter first
        flight_filter = create_filter(
            flight_data=[FlightData(date=date_str, from_airport=origin, to_airport=destination)],
            trip="one-way", seat="economy",
            passengers=Passengers(adults=adults)
        )
        # Then fetch with currency
        result: Result = get_flights_from_filter(
            flight_filter,
            currency="INR", # Specify INR currency
            mode="fallback"
        )
        print(f"  Found {len(result.flights)} flights for {origin}->{destination}. Trend: {result.current_price}")
        return {"result_obj": result, "day_of_week": day_of_week, "error": None}
    except RuntimeError as e:
        print(f"  RuntimeError for {origin}->{destination}: {e}")
        return {"result_obj": None, "day_of_week": day_of_week, "error": f"RuntimeError: {e}"}
    except Exception as e:
        print(f"  Unexpected Error for {origin}->{destination}: {e}")
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
        # Assuming INR prices might have '₹' symbol, removing it along with commas
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
    """Processes flight tracking for a single specified route."""
    print(f"\n--- Processing Route: {origin} to {destination} ({route_label}) ---")
    
    json_filepath = get_json_filename(route_label)
    master_data = load_existing_data(json_filepath)

    start_date_obj = date.today()
    end_date_obj = start_date_obj + timedelta(days=DAYS_INTO_FUTURE)
    
    current_processing_date = start_date_obj
    is_first_api_call_in_route_processing = True

    while current_processing_date <= end_date_obj:
        flight_date_str = current_processing_date.strftime("%Y-%m-%d")
        current_check_timestamp_iso = datetime.now().isoformat()

        if not is_first_api_call_in_route_processing:
            delay_seconds = random.uniform(MIN_REQUEST_DELAY, MAX_REQUEST_DELAY)
            print(f"Waiting for {delay_seconds:.2f} seconds before next daily API call for {route_label}...")
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

        historical_observation = {
            "check_timestamp": current_check_timestamp_iso,
            "cheapest_flight_in_this_check": latest_snapshot["cheapest_flight_found"],
            "google_price_trend": google_price_trend_this_check,
            "number_of_flights_found": num_flights_this_check,
            "error_if_any": error_msg
        }
        master_data["tracked_flight_dates"][flight_date_str]["hourly_observations_history"].append(historical_observation)

        if cheapest_flight_this_check_obj and cheapest_numeric_price_this_check is not None:
            current_overall_lowest = master_data["tracked_flight_dates"][flight_date_str].get("lowest_price_ever_recorded")
            new_best_price_found = False
            if current_overall_lowest is None or cheapest_numeric_price_this_check < current_overall_lowest.get("numeric_price", float('inf')):
                new_best_price_found = True
            elif cheapest_numeric_price_this_check == current_overall_lowest.get("numeric_price"):
                current_overall_lowest["last_confirmed_at"] = current_check_timestamp_iso
                if flight_date_str in master_data["lowest_price_quick_view"]:
                     master_data["lowest_price_quick_view"][flight_date_str]["last_confirmed_at"] = current_check_timestamp_iso

            if new_best_price_found:
                best_price_record = {
                    "numeric_price": cheapest_numeric_price_this_check,
                    "price_str": getattr(cheapest_flight_this_check_obj, 'price', None),
                    "flight_details": flight_to_dict(cheapest_flight_this_check_obj),
                    "first_recorded_at": current_check_timestamp_iso,
                    "last_confirmed_at": current_check_timestamp_iso
                }
                master_data["tracked_flight_dates"][flight_date_str]["lowest_price_ever_recorded"] = best_price_record
                master_data["lowest_price_quick_view"][flight_date_str] = {
                    "day_of_week": master_data["tracked_flight_dates"][flight_date_str]["day_of_week"],
                    **best_price_record
                }
        elif error_msg and flight_date_str not in master_data["lowest_price_quick_view"]:
             master_data["lowest_price_quick_view"][flight_date_str] = {
                "day_of_week": master_data["tracked_flight_dates"][flight_date_str]["day_of_week"],
                "numeric_price": None, "price_str": None, "flight_details": None,
                "first_recorded_at": None, "last_confirmed_at": None, "error": error_msg
            }
        
        print(f"  Finished processing {flight_date_str} for {route_label}.")
        current_processing_date += timedelta(days=1)

    save_data(json_filepath, master_data, origin, destination)
    print(f"--- Finished Processing Route: {origin} to {destination} ({route_label}) ---")


def run_all_routes_job():
    """Main job function to iterate through all configured routes and process them."""
    print(f"========= Master Job Started: {datetime.now().isoformat()} =========")
    for route_info in ROUTES:
        process_route_data(
            origin=route_info["origin"],
            destination=route_info["destination"],
            route_label=route_info["label"]
        )
        # Optional: Add a small delay between processing different routes if desired
        # time.sleep(random.uniform(1.0, 3.0)) 
    print(f"========= Master Job Ended: {datetime.now().isoformat()} =========")


if __name__ == "__main__":
    print(f"Script started for a single execution run via GitHub Actions.") # Updated message
    run_all_routes_job()
    print("Script execution finished.") # Updated message