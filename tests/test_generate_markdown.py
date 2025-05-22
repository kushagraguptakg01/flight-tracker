# tests/test_generate_markdown.py
import pytest
import json
import os
from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, mock_open, call 
from freezegun import freeze_time

# Assuming generate_markdown.py is in the parent directory
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
    # UTC 'Z' notation
    assert format_iso_timestamp_to_ist_string("2023-10-26T10:00:00Z") == "2023-10-26 15:30:00 IST"
    # UTC with +00:00 offset
    assert format_iso_timestamp_to_ist_string("2023-10-26T10:00:00+00:00") == "2023-10-26 15:30:00 IST"
    # Naive datetime string (should be treated as UTC as per function's logic)
    assert format_iso_timestamp_to_ist_string("2023-01-01T12:00:00") == "2023-01-01 17:30:00 IST"
    # Timestamp with another offset (-05:00)
    assert format_iso_timestamp_to_ist_string("2023-01-01T12:00:00-05:00") == "2023-01-01 22:30:00 IST" # 12:00-05:00 is 17:00 UTC, which is 22:30 IST
    # Date only output
    assert format_iso_timestamp_to_ist_string("2023-10-26T18:30:00Z", include_time=False) == "2023-10-27" 
    # Invalid timestamp
    assert format_iso_timestamp_to_ist_string("invalid-timestamp") == "N/A"
    # Timestamp with timezone Z, but include_time=False
    assert format_iso_timestamp_to_ist_string("2024-01-14T10:00:00Z", include_time=False) == "2024-01-14" # 15:30 IST is still 14th in IST date
    assert format_iso_timestamp_to_ist_string("2024-01-14T20:00:00Z", include_time=False) == "2024-01-15" # 01:30 IST on 15th


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
    assert get_lowest_price_and_details_in_period(history_zero_price, 7, today) == (None, None, None)

    # CORRECTED KEYS for flight_details
    flight_details_positive = {"name": "FlyCheap", "stops": 0, "departure": "10:00 AM", "arrival": "12:00 PM", "duration": "2h"}
    history_positive_price = [{"checked_at": "2024-01-14T10:00:00Z", "cheapest_flight_found": {"numeric_price": 5000.0, "flight_details": flight_details_positive}}]
    price, details, obs_ts = get_lowest_price_and_details_in_period(history_positive_price, 7, today)
    assert price == 5000.0
    assert details == flight_details_positive
    assert obs_ts == "2024-01-14 15:30:00 IST"

    history_multiple_positive = [
        {"checked_at": "2024-01-13T10:00:00Z", "cheapest_flight_found": {"numeric_price": 6000.0, "flight_details": {"name": "FlyMore"}}},
        {"checked_at": "2024-01-14T11:00:00Z", "cheapest_flight_found": {"numeric_price": 4500.0, "flight_details": {"name": "FlyBest"}}}, # CORRECTED KEYS not strictly needed here if only name is checked
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
    
    # Test with 14 day period
    history_for_14_days = [{"checked_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), "cheapest_flight_found": {"numeric_price": 3000.0, "flight_details": {"name": "EightDaysAgo"}}}]
    price_14, _, _ = get_lowest_price_and_details_in_period(history_for_14_days, 14, today)
    assert price_14 == 3000.0
    price_7, _, _ = get_lowest_price_and_details_in_period(history_for_14_days, 7, today)
    assert price_7 is None


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
    # "Last X Days" sections won't appear if tracked_flight_dates is empty
    assert "Lowest Prices Observed in Last 7 Days" not in md
    assert "Lowest Prices Observed in Last 14 Days" not in md

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_quick_view_data(tmp_path):
    today = date.today()
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE)) # Deep copy
    data["lowest_price_quick_view"] = {
        "2024-02-01": {
            "day_of_week": "Thursday", "numeric_price": 3000.0,
            # CORRECTED KEYS for flight_details:
            "flight_details": {"name": "QuickAir", "departure": "08:00 AM", "arrival": "10:00 AM", "duration": "2h", "stops": 0, "arrival_time_ahead": ""},
            "first_recorded_at": "2024-01-10T05:00:00Z"
        }
    }
    data_file = tmp_path / "quick.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)
    
    assert "| 2024-02-01   | Thu | ₹3,000 | N/A | 08:00 AM → 10:00 AM | QuickAir | 2h | 0 | 2024-01-10 10:30:00 IST |" in md

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_quick_view_and_current_price_data(tmp_path):
    today = date.today()
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE)) # Deep copy
    data["lowest_price_quick_view"] = {
        "2024-02-01": {
            "day_of_week": "Thursday", "numeric_price": 3000.0, # Lowest Ever
            # CORRECTED KEYS:
            "flight_details": {"name": "QuickAir", "departure": "08:00 AM", "arrival": "10:00 AM", "duration": "2h", "stops": 0, "arrival_time_ahead": ""},
            "first_recorded_at": "2024-01-10T05:00:00Z"
        }
    }
    data["tracked_flight_dates"] = {
        "2024-02-01": {
            "day_of_week": "Thursday",
            "latest_check_snapshot": {
                "google_price_trend": "typical",
                "cheapest_flight_found": {
                    "numeric_price": 3200.0, # Current price example
                    # CORRECTED KEYS:
                    "flight_details": {"name": "CurrentDayAir", "departure": "09:00 AM", "arrival": "11:00 AM", "duration": "2h", "stops": 0, "arrival_time_ahead": ""}
                }
            },
            "hourly_observations_history": [] 
        }
    }
    data_file = tmp_path / "quick_and_current.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)
    
    assert "| 2024-02-01   | Thu | ₹3,000 | ₹3,200 | 08:00 AM → 10:00 AM | QuickAir | 2h | 0 | 2024-01-10 10:30:00 IST | 📊 (Typical) |" in md

@freeze_time("2024-01-15")
def test_generate_route_markdown_with_tracked_dates(tmp_path):
    today = date.today() # 2024-01-15
    data = json.loads(json.dumps(SAMPLE_JSON_STRUCTURE)) # Deep copy
    data["tracked_flight_dates"] = {
        "2024-02-10": { # Travel date
            "day_of_week": "Saturday",
            "latest_check_snapshot": { # Current status for travel date 2024-02-10
                "google_price_trend": "high",
                "number_of_flights_found": 0 # Results in "No flights" for current price
            }, 
            "hourly_observations_history": [
                # Observation made on 2024-01-10 (within 7/14 days of 2024-01-15)
                {"checked_at": "2024-01-10T12:00:00Z", "cheapest_flight_found": {"numeric_price": 4000.0, 
                    # CORRECTED KEYS:
                    "flight_details": {"name": "HistAir1", "departure": "1PM", "arrival": "3PM", "duration": "2h", "stops": 1, "arrival_time_ahead": ""}}},
                # Observation made on 2024-01-01 (outside 7/14 days of 2024-01-15)
                {"checked_at": "2024-01-01T12:00:00Z", "cheapest_flight_found": {"numeric_price": 3000.0, "flight_details": {"name": "OldHist"}}}
            ]
        }
    }
    data_file = tmp_path / "tracked.json"
    data_file.write_text(json.dumps(data))
    md = generate_route_markdown(str(data_file), today)

    assert "### Lowest Prices Observed in Last 7 Days (For This Route)" in md
    assert "| 2024-02-10 | Sat | ₹4,000 | No flights | 1PM → 3PM | HistAir1 | 2h | 1 | 2024-01-10 17:30:00 IST |" in md
    assert "OldHist" not in md # Should not appear in 7-day table

    assert "### Lowest Prices Observed in Last 14 Days (For This Route)" in md
    assert "| 2024-02-10 | Sat | ₹4,000 | No flights | 1PM → 3PM | HistAir1 | 2h | 1 | 2024-01-10 17:30:00 IST |" in md
    assert "OldHist" not in md # Should also not appear in 14-day table as it's too old (Jan 1 vs Jan 15 check)

# --- Tests for generate_master_markdown ---

@freeze_time("2024-01-15T12:30:00Z") # UTC time
@patch('generate_markdown.generate_route_markdown')
@patch('builtins.open', new_callable=mock_open)
def test_generate_master_markdown(mock_file_write, mock_gen_route_md, tmp_path):
    # Corrected mock: generate_route_markdown returns content for one route,
    # ending with a newline, but without the inter-route '---' separator.
    mock_gen_route_md.side_effect = lambda fp, td: f"Content for {os.path.basename(fp)}\n"

    json_file1_path = tmp_path / "flight_tracker_route1.json"
    json_file1_path.write_text(json.dumps(SAMPLE_JSON_STRUCTURE))
    json_file2_path = tmp_path / "flight_tracker_route2.json"
    json_file2_path.write_text(json.dumps(SAMPLE_JSON_STRUCTURE))
    non_existent_json_path = tmp_path / "flight_tracker_route_ghost.json"

    output_md_path = tmp_path / "MASTER.md"

    # Scenario 1: Multiple valid files
    # Note: os.path.basename(str(path_object)) is fine.
    # sorted() on list of strings will sort them alphabetically.
    # flight_tracker_route1.json, flight_tracker_route2.json
    json_files_arg = sorted([str(json_file1_path), str(json_file2_path)])
    result = generate_master_markdown(json_files_arg, str(output_md_path))
    assert result is True

    today_arg = date(2024, 1, 15)
    # Calls should be in sorted order of filenames
    expected_calls = [call(str(json_file1_path), today_arg), call(str(json_file2_path), today_arg)]
    mock_gen_route_md.assert_has_calls(expected_calls, any_order=False)

    mock_file_write.assert_called_once_with(str(output_md_path), 'w', encoding='utf-8')
    written_content = "".join(c[0][0] for c in mock_file_write().write.call_args_list)

    assert "# Flight Price Summary ✈️" in written_content
    assert "_{This README is automatically updated. Last generated: 2024-01-15 18:00:00 IST}_" in written_content
    # mock returns "Content...\n", loop adds "\n---\n"
    assert f"Content for {os.path.basename(str(json_file1_path))}\n\n---\n" in written_content
    assert f"Content for {os.path.basename(str(json_file2_path))}\n\n---\n" in written_content
    assert "Powered by [GitHub Actions]" in written_content

    # Scenario 2: Mix of valid and invalid files
    mock_gen_route_md.reset_mock()
    mock_file_write.reset_mock(); mock_file_write().write.reset_mock()

    # Sorted: flight_tracker_route1.json, flight_tracker_route_ghost.json
    json_files_arg_mixed = sorted([str(json_file1_path), str(non_existent_json_path)])
    result = generate_master_markdown(json_files_arg_mixed, str(output_md_path))
    assert result is True

    # mock_gen_route_md is only called for the existing file
    mock_gen_route_md.assert_called_once_with(str(json_file1_path), today_arg)

    written_content_mixed = "".join(c[0][0] for c in mock_file_write().write.call_args_list)
    # Valid file content check
    assert f"Content for {os.path.basename(str(json_file1_path))}\n\n---\n" in written_content_mixed
    # Non-existent file message check (this was the failing part)
    # The generate_master_markdown function adds:
    # f"## Data for {basename}\n\n_File not found during Markdown generation._\n\n---\n"
    expected_ghost_header = f"## Data for {os.path.basename(str(non_existent_json_path))}"
    expected_ghost_message = "_File not found during Markdown generation._\n\n---\n"
    assert expected_ghost_header in written_content_mixed
    assert expected_ghost_message in written_content_mixed


    # Scenario 3: No JSON files
    mock_gen_route_md.reset_mock()
    mock_file_write.reset_mock(); mock_file_write().write.reset_mock()

    result = generate_master_markdown([], str(output_md_path))
    assert result is True
    mock_gen_route_md.assert_not_called()
    written_content_no_files = "".join(c[0][0] for c in mock_file_write().write.call_args_list)
    assert "_No data files specified for processing._" in written_content_no_files

    
# Test for __main__ block in generate_markdown.py
@patch('generate_markdown.generate_master_markdown')
@patch('sys.argv', ['generate_markdown.py', 'TEST_README.md', 'file1.json', 'file2.json'])
def test_main_block_with_args(mock_generate_master_markdown):
    # This import needs to happen after patching sys.argv if the script reads argv at import time
    # However, generate_markdown.py reads it inside if __name__ == "__main__"
    # To test __main__, we'd typically call a function that encapsulates its logic.
    # For now, let's assume __main__ calls generate_master_markdown correctly.
    # A more robust test would involve `runpy.run_path` or refactoring __main__.
    # This test simply checks if generate_master_markdown would be called.
    # generate_markdown.main_logic_function(["TEST_README.md", "file1.json", "file2.json"]) # If refactored
    # For this example, we'll just assert it would be called if __main__ was executed.
    # Actual execution of __main__ is tricky to test directly without subprocess or runpy.
    
    # If __main__ directly calls generate_master_markdown:
    # This test is more conceptual for now, as __main__ is not directly callable.
    # Refactoring __main__ into a function would make this testable.
    # Example if refactored:
    # generate_markdown.main(['generate_markdown.py', 'TEST_README.md', 'file1.json', 'file2.json'])
    # mock_generate_master_markdown.assert_called_once_with(['file1.json', 'file2.json'], 'TEST_README.md')
    pass # Placeholder for more direct __main__ testing if refactored.