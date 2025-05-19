# tests/test_generate_markdown.py
import pytest
import json
import os
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, mock_open, call 
from freezegun import freeze_time

# Assuming generate_markdown.py is in the parent directory
# If your project structure is different, adjust the import path.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from generate_markdown import (
    format_price,
    get_price_trend_emoji,
    extract_time,
    format_iso_timestamp_to_ist_string,
    get_lowest_price_and_details_in_period,
    generate_route_markdown,
    generate_master_markdown
)

# --- Tests for Helper Functions ---

def test_format_price():
    assert format_price(None) == "N/A"
    assert format_price(0.0) == "<span style='color:grey;'>₹0</span>"
    assert format_price(0) == "<span style='color:grey;'>₹0</span>"
    assert format_price(5000.0) == "₹5,000"
    assert format_price(12345) == "₹12,345"
    assert format_price(123.45) == "₹123" # .0f formatting
    assert format_price("invalid") == "N/A"

def test_get_price_trend_emoji():
    assert get_price_trend_emoji(None) == " "
    assert get_price_trend_emoji("N/A") == " "
    assert get_price_trend_emoji("unknown") == " "
    assert get_price_trend_emoji("low") == "📉 (Low)"
    assert get_price_trend_emoji("HIGH") == "📈 (High)" # Case-insensitive
    assert get_price_trend_emoji("Typical") == "📊 (Typical)"
    assert get_price_trend_emoji("SomethingElse") == "Somethingelse"

def test_extract_time():
    assert extract_time("10:00 AM on Date") == "10:00 AM"
    assert extract_time("10:00 AM") == "10:00 AM"
    assert extract_time(None) == "N/A"
    assert extract_time("") == "N/A"

def test_format_iso_timestamp_to_ist_string():
    assert format_iso_timestamp_to_ist_string(None) == "N/A"
    assert format_iso_timestamp_to_ist_string("") == "N/A"
    assert format_iso_timestamp_to_ist_string("2023-10-26T10:00:00Z") == "2023-10-26 15:30:00 IST"
    assert format_iso_timestamp_to_ist_string("2023-10-26T10:00:00+00:00") == "2023-10-26 15:30:00 IST"
    # Test with include_time=False
    assert format_iso_timestamp_to_ist_string("2023-10-26T18:30:00Z", include_time=False) == "2023-10-27" 
    assert format_iso_timestamp_to_ist_string("invalid-timestamp") == "N/A"


# --- Tests for get_lowest_price_and_details_in_period ---

@freeze_time("2024-01-15") 
def test_get_lowest_price_and_details_in_period_logic():
    today = date.today() # 2024-01-15

    assert get_lowest_price_and_details_in_period([], 7, today) == (None, None, None)

    history_none_price = [{"checked_at": "2024-01-14T10:00:00Z", "cheapest_flight_found": None }]
    assert get_lowest_price_and_details_in_period(history_none_price, 7, today) == (None, None, None)

    history_none_numeric_price = [{"checked_at": "2024-01-14T10:00:00Z", "cheapest_flight_found": {"numeric_price": None, "flight_details": {"name": "ErrorAir"}}}]
    assert get_lowest_price_and_details_in_period(history_none_numeric_price, 7, today) == (None, None, None)

    history_zero_price = [{"checked_at": "2024-01-14T10:00:00Z", "cheapest_flight_found": {"numeric_price": 0.0, "flight_details": {"name": "ZeroAir"}}}]
    assert get_lowest_price_and_details_in_period(history_zero_price, 7, today) == (None, None, None) # 0.0 is excluded

    flight_details_positive = {"name": "FlyCheap", "stops": 0}
    history_positive_price = [{"checked_at": "2024-01-14T10:00:00Z", "cheapest_flight_found": {"numeric_price": 5000.0, "flight_details": flight_details_positive}}]
    price, details, obs_ts = get_lowest_price_and_details_in_period(history_positive_price, 7, today)
    assert price == 5000.0
    assert details == flight_details_positive
    assert obs_ts == "2024-01-14 15:30:00 IST"

    history_multiple_positive = [
        {"checked_at": "2024-01-13T10:00:00Z", "cheapest_flight_found": {"numeric_price": 6000.0, "flight_details": {"name": "FlyMore"}}},
        {"checked_at": "2024-01-14T11:00:00Z", "cheapest_flight_found": {"numeric_price": 4500.0, "flight_details": {"name": "FlyBest"}}},
        {"checked_at": "2024-01-12T09:00:00Z", "cheapest_flight_found": {"numeric_price": 4800.0, "flight_details": {"name": "FlyGood"}}}
    ]
    price, details, obs_ts = get_lowest_price_and_details_in_period(history_multiple_positive, 7, today)
    assert price == 4500.0
    assert details["name"] == "FlyBest"
    assert obs_ts == "2024-01-14 16:30:00 IST"

    history_mixed = [
        {"checked_at": "2024-01-13T10:00:00Z", "cheapest_flight_found": {"numeric_price": 0.0, "flight_details": {"name": "ZeroFly"}}},
        {"checked_at": "2024-01-14T11:00:00Z", "cheapest_flight_found": {"numeric_price": 200.0, "flight_details": {"name": "TwoHundred"}}},
    ]
    price, details, obs_ts = get_lowest_price_and_details_in_period(history_mixed, 7, today)
    assert price == 200.0
    assert details["name"] == "TwoHundred"

    history_outside_period = [{"checked_at": "2024-01-01T10:00:00Z", "cheapest_flight_found": {"numeric_price": 3000.0, "flight_details": {"name": "OldFly"}}}]
    assert get_lowest_price_and_details_in_period(history_outside_period, 7, today) == (None, None, None)

    history_boundary = [{"checked_at": "2024-01-09T00:00:01Z", "cheapest_flight_found": {"numeric_price": 7000.0, "flight_details": {"name": "BoundaryFly"}}}]
    price, details, obs_ts = get_lowest_price_and_details_in_period(history_boundary, 7, today)
    assert price == 7000.0
    assert details["name"] == "BoundaryFly"

    history_malformed = [
        {"checked_at": "2024-01-14T10:00:00Z"}, 
        {"checked_at": "2024-01-13T10:00:00Z", "cheapest_flight_found": {"flight_details": {"name": "NoPrice"}}}
    ]
    assert get_lowest_price_and_details_in_period(history_malformed, 7, today) == (None, None, None)


# --- Tests for generate_route_markdown ---

SAMPLE_JSON_STRUCTURE = {
    "meta_info": {
        "origin": "DEL", "destination": "BOM",
        "script_last_successful_run_timestamp": "2024-01-15T10:00:00Z"
    },
    "lowest_price_quick_view": {},
    "tracked_flight_dates": {}
}

@freeze_time("2024-01-15")
def test_generate_route_markdown_file_not_found(tmp_path):
    today = date.today()
    non_existent_file = tmp_path / "ghost.json"
    md = generate_route_markdown(str(non_existent_file), today)
    assert "ghost.json" in md
    assert "_File not found._" in md

@freeze_time("2024-01-15")
def test_generate_route_markdown_malformed_json(tmp_path):
    today = date.today()
    malformed_file = tmp_path / "bad.json"
    malformed_file.write_text("{not_json:")
    md = generate_route_markdown(str(malformed_file), today)
    assert "bad.json" in md
    assert "_Error loading/parsing" in md

@freeze_time("2024-01-15")
def test_generate_route_markdown_empty_data(tmp_path):
    today = date.today()
    empty_data_file = tmp_path / "empty.json"
    empty_data_file.write_text(json.dumps(SAMPLE_JSON_STRUCTURE))
    md = generate_route_markdown(str(empty_data_file), today)
    assert "✈️ Flight Prices: DEL ➔ BOM" in md
    assert "_Last data update for this route: 2024-01-15 15:30:00 IST" in md
    assert "### Current Overall Lowest Prices by Travel Date" in md
    assert "_No overall lowest price data available._" in md
    assert "### Lowest Prices Observed in Last 7 Days (For This Route)" not in md # Corrected: This section won't appear
    assert "### Lowest Prices Observed in Last 14 Days (For This Route)" not in md # Corrected: This section won't appear

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_quick_view_data(tmp_path):
    today = date.today()
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE))
    data["lowest_price_quick_view"] = {
        "2024-02-01": {
            "day_of_week": "Thursday", "numeric_price": 3000.0,
            "flight_details": {"name": "QuickAir", "departure_time": "08:00 AM", "arrival_time": "10:00 AM", "duration_str": "2h", "stops": 0, "arrival_time_ahead": ""},
            "first_recorded_at": "2024-01-10T05:00:00Z"
        },
        "2024-02-02": { # Test for 0.0 price in quick view
            "day_of_week": "Friday", "numeric_price": 0.0,
            "flight_details": {"name": "ZeroQuick", "departure_time": "N/A", "arrival_time": "N/A", "duration_str": "N/A", "stops": "Unknown", "arrival_time_ahead": ""},
            "first_recorded_at": "2024-01-11T06:00:00Z"
        }
    }
    # IMPORTANT: For this test to accurately check the "Current Price" column,
    # you might also want to add a corresponding entry in data["tracked_flight_dates"]
    # if you want to test a scenario where "Current Price" is populated.
    # If data["tracked_flight_dates"] remains empty for "2024-02-01",
    # then "Current Price" for that date will be "N/A".

    data_file = tmp_path / "quick.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)

    # Corrected assertion: includes the "N/A" for the new "Current Price" column
    assert "| 2024-02-01   | Thu | ₹3,000 | N/A | 08:00 AM → 10:00 AM | QuickAir" in md
    assert "| 2024-02-02   | Fri | <span style='color:grey;'>₹0</span> | N/A | N/A → N/A | ZeroQuick" in md # Current Price will also be N/A
    assert "2024-01-10 10:30:00 IST |" in md # Found on date for quick view

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_quick_view_and_current_price_data(tmp_path):
    today = date.today()
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE))
    data["lowest_price_quick_view"] = {
        "2024-02-01": {
            "day_of_week": "Thursday", "numeric_price": 3000.0, # Lowest Ever
            "flight_details": {"name": "QuickAir", "departure_time": "08:00 AM", "arrival_time": "10:00 AM", "duration_str": "2h", "stops": 0, "arrival_time_ahead": ""},
            "first_recorded_at": "2024-01-10T05:00:00Z"
        }
    }
    data["tracked_flight_dates"] = { # Add this to test the "Current Price" column
        "2024-02-01": {
            "day_of_week": "Thursday", # Should match or be consistent
            "latest_check_snapshot": {
                "google_price_trend": "typical",
                "cheapest_flight_found": {
                    "numeric_price": 3200.0, # Current price example
                    "flight_details": {"name": "CurrentDayAir", "departure_time": "09:00 AM", "arrival_time": "11:00 AM", "duration_str": "2h", "stops": 0, "arrival_time_ahead": ""}
                }
            },
            "hourly_observations_history": [] # Can be empty for this specific test focus
        }
    }

    data_file = tmp_path / "quick_and_current.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)

    # Now assert with the populated "Current Price"
    assert "| 2024-02-01   | Thu | ₹3,000 | ₹3,200 | 08:00 AM → 10:00 AM | QuickAir" in md
    assert "2024-01-10 10:30:00 IST | 📊 (Typical) |" in md # Check trend as well

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_tracked_dates(tmp_path):
    today = date.today()
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE))
    data["tracked_flight_dates"] = {
        "2024-02-10": {
            "day_of_week": "Saturday",
            # To test the "Current Price" column properly in "Last X Days",
            # this latest_check_snapshot should ideally contain a "cheapest_flight_found"
            # or "error_if_any" or "number_of_flights_found".
            # For this specific test, we'll keep it as is and expect "No flights".
            "latest_check_snapshot": {"google_price_trend": "high"}, # No cheapest_flight_found here
            "hourly_observations_history": [
                {"checked_at": "2024-01-10T12:00:00Z", "cheapest_flight_found": {"numeric_price": 4000.0, "flight_details": {"name": "HistAir1", "departure_time": "1PM", "arrival_time": "3PM", "duration_str": "2h", "stops": 1, "arrival_time_ahead": ""}}},
                {"checked_at": "2024-01-11T12:00:00Z", "cheapest_flight_found": {"numeric_price": 0.0, "flight_details": {"name": "ZeroHist"}}}, # Will be ignored by get_lowest_price_and_details_in_period
                {"checked_at": "2024-01-01T12:00:00Z", "cheapest_flight_found": {"numeric_price": 3000.0, "flight_details": {"name": "OldHist"}}} # Outside 7/14 day window
            ]
        }
    }
    data_file = tmp_path / "tracked.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)

    assert "### Lowest Prices Observed in Last 7 Days (For This Route)" in md
    # Corrected assertion for the table row, including the "Current Price" column
    # | Travel Date | Day | Lowest in Period | Current Price | Dep → Arr (Details) | Airline | ...
    assert "| 2024-02-10 | Sat | ₹4,000 | No flights | 1PM → 3PM | HistAir1" in md
    assert "2024-01-10 17:30:00 IST |" in md
    assert "ZeroHist" not in md
    assert "OldHist" not in md

    assert "### Lowest Prices Observed in Last 14 Days (For This Route)" in md
    assert "| 2024-02-10 | Sat | ₹4,000 | No flights | 1PM → 3PM | HistAir1" in md

# --- Tests for generate_master_markdown ---

@freeze_time("2024-01-15T12:30:00Z") 
@patch('generate_markdown.generate_route_markdown') 
@patch('builtins.open', new_callable=mock_open) 
def test_generate_master_markdown(mock_file_write, mock_gen_route_md, tmp_path):
    mock_gen_route_md.side_effect = lambda fp, td: f"Content for {os.path.basename(fp)}\n"
    
    json_file1 = tmp_path / "route1.json"
    json_file1.write_text(json.dumps(SAMPLE_JSON_STRUCTURE))
    json_file2 = tmp_path / "route2.json"
    json_file2.write_text(json.dumps(SAMPLE_JSON_STRUCTURE))
    non_existent_json = tmp_path / "route_ghost.json" 
    
    output_md = tmp_path / "MASTER.md"
    
    # Scenario 1: Multiple valid files
    json_files_arg = [str(json_file1), str(json_file2)]
    result = generate_master_markdown(json_files_arg, str(output_md))
    assert result is True
    
    today_arg = date.today() # 2024-01-15
    expected_calls = [call(str(json_file1), today_arg), call(str(json_file2), today_arg)]
    mock_gen_route_md.assert_has_calls(expected_calls, any_order=True) 

    mock_file_write.assert_called_once_with(str(output_md), 'w', encoding='utf-8')
    written_content = "".join(c[0][0] for c in mock_file_write().write.call_args_list)
    
    assert "# Flight Price Summary ✈️" in written_content
    assert "_{This README is automatically updated. Last generated: 2024-01-15 18:00:00 IST}_" in written_content # Corrected assertion
    assert "Content for route1.json" in written_content
    assert "Content for route2.json" in written_content
    assert "\n---\n" in written_content 
    assert "Powered by [GitHub Actions]" in written_content

    # Scenario 2: Mix of valid and invalid files
    mock_gen_route_md.reset_mock()
    mock_file_write.reset_mock()
    mock_file_write().write.reset_mock()

    json_files_arg_mixed = [str(json_file1), str(non_existent_json)]
    result = generate_master_markdown(json_files_arg_mixed, str(output_md))
    assert result is True
    mock_gen_route_md.assert_called_once_with(str(json_file1), today_arg) 
    
    written_content_mixed = "".join(c[0][0] for c in mock_file_write().write.call_args_list)
    assert "Content for route1.json" in written_content_mixed
    assert "## Data for route_ghost.json" in written_content_mixed
    assert "_File not found during Markdown generation._" in written_content_mixed

    # Scenario 3: No JSON files
    mock_gen_route_md.reset_mock()
    mock_file_write.reset_mock()
    mock_file_write().write.reset_mock()

    result = generate_master_markdown([], str(output_md))
    assert result is True
    mock_gen_route_md.assert_not_called()
    written_content_no_files = "".join(c[0][0] for c in mock_file_write().write.call_args_list)
    assert "_No data files specified for processing._" in written_content_no_files

# Note: Tests for the __main__ block are omitted here for brevity
# but it's recommended to refactor that block into a callable function for easier testing.