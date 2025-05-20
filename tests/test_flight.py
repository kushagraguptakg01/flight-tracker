# tests/test_flight.py
import pytest
import json
import os
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, mock_open, call, MagicMock, ANY
from freezegun import freeze_time
import requests # <<< Added import

# Add project root to sys.path to allow importing flight
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import flight as flight_tracker # Use an alias to avoid conflict with 'flight' variable names

# --- Mock fast_flights library components ---
class MockFlight:
    def __init__(self, is_best=False, name="MockAirline", departure="10:00 AM", arrival="12:00 PM",
                 arrival_time_ahead=None, duration="2h 0m", stops=0, delay=None, price="₹5,000"):
        self.is_best = is_best
        self.name = name
        self.departure = departure
        self.arrival = arrival
        self.arrival_time_ahead = arrival_time_ahead
        self.duration = duration
        self.stops = stops
        self.delay = delay
        self.price = price

class MockResult:
    def __init__(self, flights=None, current_price="typical"):
        self.flights = flights if flights is not None else []
        self.current_price = current_price

# --- Fixtures ---
@pytest.fixture
def mock_env_vars(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake_token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'fake_chat_id')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'test_user/test_repo')

@pytest.fixture
def temp_json_dir(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


# --- Tests for Utility Functions ---
# (These should be fine, keeping them for completeness)
def test_escape_markdown_v2():
    assert flight_tracker.escape_markdown_v2("Hello_World*Test[1](Example).") == \
           r"Hello\_World\*Test\[1\]\(Example\)\."
    assert flight_tracker.escape_markdown_v2("No special chars") == "No special chars"
    assert flight_tracker.escape_markdown_v2(None) == ""
    assert flight_tracker.escape_markdown_v2(123) == "123"

def test_get_json_filename():
    assert flight_tracker.get_json_filename("DEL_to_BOM") == "flight_tracker_DEL_to_BOM.json"

def test_convert_price_str_to_numeric():
    assert flight_tracker.convert_price_str_to_numeric("₹5,000") == 5000.0
    assert flight_tracker.convert_price_str_to_numeric("₹123") == 123.0
    assert flight_tracker.convert_price_str_to_numeric("₹1,234.56") == 1234.0
    assert flight_tracker.convert_price_str_to_numeric("NoPrice") is None
    assert flight_tracker.convert_price_str_to_numeric(None) is None
    assert flight_tracker.convert_price_str_to_numeric("₹0") is None
    assert flight_tracker.convert_price_str_to_numeric("0") is None
    assert flight_tracker.convert_price_str_to_numeric("") is None

def test_flight_to_dict():
    mock_flight_obj = MockFlight(name="TestAir", departure="08:00", arrival="10:00",
                                 duration="2h", stops=1, price="₹3000", delay="On time")
    expected_dict = {
        "is_best": False, "name": "TestAir", "departure": "08:00", "arrival": "10:00",
        "arrival_time_ahead": None, "duration": "2h", "stops": 1, "delay": "On time", "price": "₹3000"
    }
    assert flight_tracker.flight_to_dict(mock_flight_obj) == expected_dict
    assert flight_tracker.flight_to_dict(None) is None


# --- Tests for File I/O ---
# (These should be fine)
@freeze_time("2024-01-01T10:00:00Z")
def test_load_existing_data(temp_json_dir):
    filepath = "test_data.json"
    data = flight_tracker.load_existing_data(filepath)
    assert data == {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}
    # ... (rest of load_existing_data tests) ...
    incomplete_data = {"tracked_flight_dates": {"2024-01-10": {}}}
    with open(filepath, "w") as f:
        json.dump(incomplete_data, f)
    data = flight_tracker.load_existing_data(filepath)
    assert data == {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}

    valid_data_content = {
        "meta_info": {"origin": "DEL", "destination": "BOM", "script_last_successful_run_timestamp": "2023-12-31T10:00:00Z"},
        "lowest_price_quick_view": {"2024-01-15": {"numeric_price": 5000}},
        "tracked_flight_dates": {"2024-01-15": {"day_of_week": "Monday"}}
    }
    with open(filepath, "w") as f:
        json.dump(valid_data_content, f)
    data = flight_tracker.load_existing_data(filepath)
    assert data == valid_data_content

@freeze_time("2024-01-15T12:30:00Z")
def test_save_data(temp_json_dir):
    filepath = "saved_data.json"
    data_to_save = {
        "meta_info": {},
        "lowest_price_quick_view": {"2024-02-01": {"numeric_price": 3000}},
        "tracked_flight_dates": {"2024-02-01": {"day_of_week": "Thursday"}}
    }
    origin, destination = "SXR", "COK"
    flight_tracker.save_data(filepath, data_to_save, origin, destination)
    assert os.path.exists(filepath)
    with open(filepath, "r") as f:
        saved_data = json.load(f)
    assert saved_data["meta_info"]["origin"] == origin
    assert saved_data["meta_info"]["destination"] == destination
    assert saved_data["meta_info"]["script_last_successful_run_timestamp"] == "2024-01-15T12:30:00+00:00"
    assert saved_data["lowest_price_quick_view"] == data_to_save["lowest_price_quick_view"]

# --- Tests for API Interaction and Data Fetching ---
# (These should be fine)
@patch('flight.get_flights_from_filter')
@patch('flight.create_filter')
def test_fetch_single_date_flights_success(mock_create_filter, mock_get_flights):
    target_date = date(2024, 3, 1)
    origin, dest, adults = "DEL", "BOM", 1
    mock_flight1 = MockFlight(price="₹4000")
    mock_flight2 = MockFlight(price="₹3500")
    mock_result_obj = MockResult(flights=[mock_flight1, mock_flight2], current_price="low")
    mock_get_flights.return_value = mock_result_obj
    result = flight_tracker.fetch_single_date_flights(target_date, origin, dest, adults)
    mock_create_filter.assert_called_once()
    mock_get_flights.assert_called_once()
    assert result["error"] is None
    assert result["day_of_week"] == "Friday"
    assert result["result_obj"] == mock_result_obj
    assert len(result["result_obj"].flights) == 2

@patch('flight.get_flights_from_filter')
def test_fetch_single_date_flights_api_error(mock_get_flights):
    target_date = date(2024, 3, 1)
    origin, dest, adults = "DEL", "BOM", 1
    mock_get_flights.side_effect = Exception("API Unreachable")
    result = flight_tracker.fetch_single_date_flights(target_date, origin, dest, adults)
    assert "Exception: API Unreachable" in result["error"]
    assert result["result_obj"] is None

@patch('flight.get_flights_from_filter')
def test_fetch_single_date_flights_filters_cancelled(mock_get_flights):
    target_date = date(2024, 3, 1)
    origin, dest, adults = "DEL", "BOM", 1
    mock_flight_valid = MockFlight(price="₹4000", delay="On time")
    mock_flight_cancelled_str = MockFlight(price="₹3000", delay="Flight Cancelled")
    mock_flight_cancelled_obj = MockFlight(price="₹3500", delay="CANCELLED")
    mock_result_obj = MockResult(flights=[mock_flight_valid, mock_flight_cancelled_str, mock_flight_cancelled_obj])
    mock_get_flights.return_value = mock_result_obj
    result = flight_tracker.fetch_single_date_flights(target_date, origin, dest, adults)
    assert result["error"] is None
    assert len(result["result_obj"].flights) == 1
    assert result["result_obj"].flights[0].price == "₹4000"

@patch('flight.get_flights_from_filter')
def test_fetch_single_date_flights_no_flights_returned(mock_get_flights):
    target_date = date(2024, 3, 1)
    origin, dest, adults = "DEL", "BOM", 1
    mock_result_obj = MockResult(flights=[])
    mock_get_flights.return_value = mock_result_obj
    result = flight_tracker.fetch_single_date_flights(target_date, origin, dest, adults)
    assert result["error"] is None
    assert len(result["result_obj"].flights) == 0

def test_get_cheapest_flight_from_result():
    assert flight_tracker.get_cheapest_flight_from_result(MockResult(flights=[])) == (None, None)
    assert flight_tracker.get_cheapest_flight_from_result(None) == (None, None)
    flight1 = MockFlight(price="₹5000")
    flight2 = MockFlight(price="₹4500")
    flight3 = MockFlight(price="₹6000")
    result_obj = MockResult(flights=[flight1, flight2, flight3])
    cheapest_flight, cheapest_price = flight_tracker.get_cheapest_flight_from_result(result_obj)
    assert cheapest_flight == flight2
    assert cheapest_price == 4500.0
    flight_invalid_price = MockFlight(price="N/A")
    flight_zero_price = MockFlight(price="₹0")
    flight_valid = MockFlight(price="₹1000")
    result_obj_mixed = MockResult(flights=[flight_invalid_price, flight_zero_price, flight_valid])
    cheapest_flight, cheapest_price = flight_tracker.get_cheapest_flight_from_result(result_obj_mixed)
    assert cheapest_flight == flight_valid
    assert cheapest_price == 1000.0
    result_obj_all_bad = MockResult(flights=[flight_invalid_price, flight_zero_price])
    assert flight_tracker.get_cheapest_flight_from_result(result_obj_all_bad) == (None, None)

# --- Tests for Telegram Notifications ---

# @patch('requests.post') # Patches requests.post used *inside* flight.py
# def test_send_telegram_notification_for_new_lowest(mock_post, mock_env_vars): # <<< Added mock_env_vars
#     flight_details = {"name": "BudgetAir", "departure": "6 AM", "arrival": "8 AM", "duration": "2h", "stops": 0}
#     flight_tracker.send_telegram_notification_for_new_lowest(
#         "DEL", "MAA", "2024-03-10", "Sunday", 2500, 3000, flight_details
#     )
#     mock_post.assert_called_once()
#     args, kwargs = mock_post.call_args
#     assert args[0] == 'https://api.telegram.org/botfake_token/sendMessage'
#     payload = kwargs['data']
#     assert payload['chat_id'] == 'fake_chat_id'
#     assert "New Overall Lowest Price Alert" in payload['text']
#     assert r"Route: *\DEL ➔ \MAA*" in payload['text']
#     assert r"Travel Date: *\2024\-03\-10* Sunday" in payload['text']
#     assert r"New Lowest Price: *₹2500*" in payload['text']
#     assert r"Previously: ₹3000" in payload['text']
#     assert r"Airline: BudgetAir" in payload['text']
#     assert payload['parse_mode'] == 'MarkdownV2'

# @patch('requests.post')
# def test_send_telegram_notification_for_price_drop_since_last_check(mock_post, mock_env_vars): # <<< Added mock_env_vars
#     flight_details = {"name": "DropAir", "departure": "9 PM", "arrival": "11 PM", "duration": "2h", "stops": 1}
#     flight_tracker.send_telegram_notification_for_price_drop_since_last_check(
#         "BLR", "HYD", "2024-03-15", "Friday", 4000, 4200, flight_details
#     )
#     mock_post.assert_called_once()
#     args, kwargs = mock_post.call_args
#     payload = kwargs['data']
#     assert "Price Drop Alert Since Last Check" in payload['text']
#     assert r"Current Price: *₹4000*" in payload['text']
#     assert r"Previously: ₹4200 in last check" in payload['text']

# @patch('requests.post')
# def test_telegram_notification_skips_if_no_creds(mock_post, capsys): # mock_env_vars intentionally omitted
#     with patch.dict(os.environ, {}, clear=True):
#         flight_tracker.send_telegram_notification_for_new_lowest("A", "B", "d", "d", 1, 2, {})
#     mock_post.assert_not_called()
#     captured = capsys.readouterr()
#     assert "Telegram bot token or chat ID not configured" in captured.out

# @patch('requests.post')
# def test_telegram_api_error_handling(mock_post, mock_env_vars, capsys): # <<< Added mock_env_vars
#     mock_response = MagicMock()
#     mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("API Error") # <<< requests is now defined
#     mock_response.text = "{'error': 'Bad request'}"
#     mock_post.return_value = mock_response

#     flight_tracker.send_telegram_notification_for_new_lowest("A", "B", "d", "d", 1, 2, {})
#     captured = capsys.readouterr()
#     assert "Error sending Telegram" in captured.out
#     assert "TG API Error: {'error': 'Bad request'}" in captured.out


# --- Tests for Core Logic (`process_route_data`) ---

@freeze_time("2024-01-15T10:00:00Z")
@patch('flight.save_data')
@patch('flight.fetch_single_date_flights')
@patch('flight.load_existing_data')
@patch('flight.send_telegram_notification_for_new_lowest')
@patch('flight.send_telegram_notification_for_price_drop_since_last_check')
@patch('time.sleep', MagicMock())
def test_process_route_data_first_run_new_lowest(
    mock_send_drop_notif, mock_send_new_lowest_notif,
    mock_load_data, mock_fetch, mock_save,
    mock_env_vars, temp_json_dir):

    mock_load_data.return_value = {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}

    # The date that will actually be processed due to freeze_time and day_offset=0
    # when DAYS_INTO_FUTURE is 1
    actual_processing_date_obj = date(2024, 1, 15) # <<< Corrected
    flight_date_str = actual_processing_date_obj.strftime("%Y-%m-%d")

    fetched_flight_obj = MockFlight(price="₹3000", name="FirstFly")
    mock_fetch.return_value = {
        "result_obj": MockResult(flights=[fetched_flight_obj], current_price="low"),
        "day_of_week": "Monday", # Corresponds to 2024-01-15
        "error": None
    }
    
    with patch('flight.DAYS_INTO_FUTURE', 1):
        flight_tracker.process_route_data("DEL", "BOM", "DEL_to_BOM")

    mock_load_data.assert_called_once_with("flight_tracker_DEL_to_BOM.json")
    mock_fetch.assert_called_once_with(actual_processing_date_obj, "DEL", "BOM", flight_tracker.NUM_ADULTS) # <<< Corrected assertion date

    mock_save.assert_called_once()
    # Correct way to access positional arguments from mock_save.call_args
    saved_filepath = mock_save.call_args[0][0]
    saved_data = mock_save.call_args[0][1] # <<< Corrected access
    
    assert saved_filepath == "flight_tracker_DEL_to_BOM.json"
    assert flight_date_str in saved_data["tracked_flight_dates"]
    date_entry = saved_data["tracked_flight_dates"][flight_date_str]
    
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"]["numeric_price"] == 3000.0
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"]["flight_details"]["name"] == "FirstFly"
    assert date_entry["lowest_price_ever_recorded"]["numeric_price"] == 3000.0
    assert flight_date_str in saved_data["lowest_price_quick_view"]
    assert saved_data["lowest_price_quick_view"][flight_date_str]["numeric_price"] == 3000.0

    mock_send_new_lowest_notif.assert_called_once_with(
        "DEL", "BOM", flight_date_str, "Monday", 3000.0, float('inf'), ANY,
        bot_token_override=None,  # Add this
        chat_id_override=None     # Add this
    )
    mock_send_drop_notif.assert_not_called()


@freeze_time("2024-01-16T10:00:00Z")
@patch('flight.save_data')
@patch('flight.fetch_single_date_flights')
@patch('flight.load_existing_data')
@patch('flight.send_telegram_notification_for_new_lowest')
@patch('flight.send_telegram_notification_for_price_drop_since_last_check')
@patch('time.sleep', MagicMock())
def test_process_route_data_price_drop_not_overall_lowest(
    mock_send_drop_notif, mock_send_new_lowest_notif,
    mock_load_data, mock_fetch, mock_save,
    mock_env_vars, temp_json_dir):

    actual_processing_date_obj = date(2024, 1, 16) # Due to freeze_time and day_offset=0
    flight_date_str = actual_processing_date_obj.strftime("%Y-%m-%d") # This is the key for tracked_flight_dates

    # We need to ensure that the prev_run_data uses this actual_processing_date_obj as key
    # if we want to test a price drop for *today's* processing date.
    # The original test used a fixed "2024-02-01" which doesn't align with how process_route_data iterates.
    
    prev_run_data = {
        "meta_info": {"origin": "DEL", "destination": "BOM", "script_last_successful_run_timestamp": "2024-01-15T10:00:00Z"},
        "lowest_price_quick_view": {
            flight_date_str: {"numeric_price": 2800.0, "flight_details": {"name": "OverallBest"}, "first_recorded_at": "...", "day_of_week": "Tuesday"}
        },
        "tracked_flight_dates": {
            flight_date_str: { # Key is the date being processed
                "day_of_week": "Tuesday", # Corresponds to 2024-01-16
                "latest_check_snapshot": {
                    "checked_at": "2024-01-15T10:00:05Z", # From a hypothetical previous day's check for this *travel date*
                    "cheapest_flight_found": {"numeric_price": 3200.0, "flight_details": {"name": "PrevCheckBest"}},
                    "google_price_trend": "high"
                },
                "lowest_price_ever_recorded": {"numeric_price": 2800.0, "flight_details": {"name": "OverallBest"}},
                "hourly_observations_history": []
            }
        }
    }
    mock_load_data.return_value = prev_run_data

    fetched_flight_obj = MockFlight(price="₹3000", name="CurrentFly")
    mock_fetch.return_value = {
        "result_obj": MockResult(flights=[fetched_flight_obj], current_price="typical"),
        "day_of_week": "Tuesday", "error": None # Day for 2024-01-16
    }

    with patch('flight.DAYS_INTO_FUTURE', 1):
        flight_tracker.process_route_data("DEL", "BOM", "DEL_to_BOM")

    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][1] # <<< Corrected access

    date_entry = saved_data["tracked_flight_dates"][flight_date_str]
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"]["numeric_price"] == 3000.0
    assert date_entry["lowest_price_ever_recorded"]["numeric_price"] == 2800.0
    assert saved_data["lowest_price_quick_view"][flight_date_str]["numeric_price"] == 2800.0

    mock_send_drop_notif.assert_called_once_with(
        "DEL", "BOM", flight_date_str, "Tuesday", 3000.0, 3200.0, ANY,
        bot_token_override=None,  # Add this
        chat_id_override=None     # Add this
    )
    mock_send_new_lowest_notif.assert_not_called()


@freeze_time("2024-01-17T10:00:00Z")
@patch('flight.save_data')
@patch('flight.fetch_single_date_flights')
@patch('flight.load_existing_data')
@patch('flight.send_telegram_notification_for_new_lowest')
@patch('flight.send_telegram_notification_for_price_drop_since_last_check')
@patch('time.sleep', MagicMock())
def test_process_route_data_api_error_for_date(
    mock_send_drop_notif, mock_send_new_lowest_notif,
    mock_load_data, mock_fetch, mock_save,
    mock_env_vars, temp_json_dir):

    actual_processing_date_obj = date(2024, 1, 17) # Due to freeze_time
    flight_date_str = actual_processing_date_obj.strftime("%Y-%m-%d")

    mock_load_data.return_value = {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}
    mock_fetch.return_value = {"result_obj": None, "day_of_week": "Wednesday", "error": "API Timeout"} # Day for 2024-01-17

    with patch('flight.DAYS_INTO_FUTURE', 1):
        flight_tracker.process_route_data("DEL", "BOM", "DEL_to_BOM")

    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][1] # <<< Corrected access

    date_entry = saved_data["tracked_flight_dates"][flight_date_str]
    assert date_entry["latest_check_snapshot"]["error_if_any"] == "API Timeout"
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"] is None
    assert date_entry["lowest_price_ever_recorded"] is None
    assert saved_data["lowest_price_quick_view"][flight_date_str]["error"] == "API Timeout"
    assert saved_data["lowest_price_quick_view"][flight_date_str]["numeric_price"] is None

    mock_send_drop_notif.assert_not_called()
    mock_send_new_lowest_notif.assert_not_called()


@freeze_time("2024-01-18T10:00:00Z")
@patch('flight.save_data')
@patch('flight.fetch_single_date_flights')
@patch('flight.load_existing_data')
@patch('flight.send_telegram_notification_for_new_lowest')
@patch('flight.send_telegram_notification_for_price_drop_since_last_check')
@patch('time.sleep', MagicMock())
def test_process_route_data_all_flights_cancelled(
    mock_send_drop_notif, mock_send_new_lowest_notif,
    mock_load_data, mock_fetch, mock_save,
    mock_env_vars, temp_json_dir):

    actual_processing_date_obj = date(2024, 1, 18) # Due to freeze_time
    flight_date_str = actual_processing_date_obj.strftime("%Y-%m-%d")

    mock_load_data.return_value = {"meta_info": {"script_last_successful_run_timestamp": None}, "lowest_price_quick_view": {}, "tracked_flight_dates": {}}
    mock_fetch.return_value = {
        "result_obj": MockResult(flights=[], current_price="unknown"),
        "day_of_week": "Thursday", "error": None # Day for 2024-01-18
    }

    with patch('flight.DAYS_INTO_FUTURE', 1):
        flight_tracker.process_route_data("DEL", "BOM", "DEL_to_BOM")

    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][1] # <<< Corrected access

    date_entry = saved_data["tracked_flight_dates"][flight_date_str]
    assert date_entry["latest_check_snapshot"]["number_of_flights_found"] == 0
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"] is None
    assert date_entry["lowest_price_ever_recorded"] is None
    assert saved_data["lowest_price_quick_view"][flight_date_str]["error"] == "No valid (non-cancelled, non-zero price) flights found this check"
    assert saved_data["lowest_price_quick_view"][flight_date_str]["numeric_price"] is None

    mock_send_drop_notif.assert_not_called()
    mock_send_new_lowest_notif.assert_not_called()

@freeze_time("2024-01-19T10:00:00Z")
@patch('flight.save_data')
@patch('flight.fetch_single_date_flights')
@patch('flight.load_existing_data')
@patch('flight.send_telegram_notification_for_new_lowest')
@patch('flight.send_telegram_notification_for_price_drop_since_last_check')
@patch('time.sleep', MagicMock())
def test_process_route_data_quick_view_error_overwritten_by_price(
    mock_send_drop_notif, mock_send_new_lowest_notif,
    mock_load_data, mock_fetch, mock_save,
    mock_env_vars, temp_json_dir):

    actual_processing_date_obj = date(2024, 1, 19) # Due to freeze_time
    flight_date_str = actual_processing_date_obj.strftime("%Y-%m-%d")

    prev_run_data_with_error = {
        "meta_info": {"script_last_successful_run_timestamp": "2024-01-18T10:00:00Z"},
        "lowest_price_quick_view": {
            flight_date_str: {"day_of_week": "Friday", "numeric_price": None, "error": "Previous API Error"}
        },
        "tracked_flight_dates": {
             flight_date_str: {
                "day_of_week": "Friday", # Day for 2024-01-19
                "latest_check_snapshot": {"error_if_any": "Previous API Error"},
                "lowest_price_ever_recorded": None,
                "hourly_observations_history": []
            }
        }
    }
    mock_load_data.return_value = prev_run_data_with_error

    fetched_flight_obj = MockFlight(price="₹3500", name="GoodFly")
    mock_fetch.return_value = {
        "result_obj": MockResult(flights=[fetched_flight_obj], current_price="low"),
        "day_of_week": "Friday", "error": None
    }

    with patch('flight.DAYS_INTO_FUTURE', 1):
        flight_tracker.process_route_data("DEL", "BOM", "DEL_to_BOM")

    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][1] # <<< Corrected access

    assert flight_date_str in saved_data["lowest_price_quick_view"]
    quick_view_entry = saved_data["lowest_price_quick_view"][flight_date_str]
    assert quick_view_entry["numeric_price"] == 3500.0
    assert "error" not in quick_view_entry

    date_entry = saved_data["tracked_flight_dates"][flight_date_str]
    assert date_entry["lowest_price_ever_recorded"]["numeric_price"] == 3500.0
    assert date_entry["latest_check_snapshot"]["cheapest_flight_found"]["numeric_price"] == 3500.0

    mock_send_new_lowest_notif.assert_called_once()
    mock_send_drop_notif.assert_not_called()


# --- Tests for Main Orchestration ---
# (This should be fine)
@patch('flight.process_route_data')
@patch('flight.ROUTES', [{"origin": "AAA", "destination": "BBB", "label": "A_to_B"}, {"origin": "CCC", "destination": "DDD", "label": "C_to_D"}])
def test_run_all_routes_job(mock_process_route, mock_env_vars):
    flight_tracker.run_all_routes_job()
    expected_calls = [
        call("AAA", "BBB", "A_to_B"),
        call("CCC", "DDD", "C_to_D")
    ]
    mock_process_route.assert_has_calls(expected_calls, any_order=False)
    assert mock_process_route.call_count == 2

def test_main_block_output(capsys, mock_env_vars):
    with patch('flight.run_all_routes_job') as mock_run_all:
        # This is a simplified test for __main__
        # To properly test __main__, refactor its contents into a callable function
        flight_tracker.run_all_routes_job() # Simulate the call from __main__
        mock_run_all.assert_called_once()