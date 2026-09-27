from datetime import datetime, timezone

from app.data.briefing import weather_note, weather_text
from app.data.weather_words import rain_desc
from app.get_weather_forecast import game_window


def _forecast():
    hours = [f"2026-09-27T{h:02d}:00" for h in range(15, 23)]
    return {"hourly": {
        "time": hours,
        "temperature_2m": [60, 62, 64, 65, 66, 66, 65, 64],
        "wind_speed_10m": [8, 9, 12, 14, 18, 16, 10, 8],
        "wind_gusts_10m": [15, 18, 29, 30, 34, 31, 20, 15],
        "wind_direction_10m": [50] * 8,
        "precipitation_probability": [10, 20, 31, 45, 60, 55, 20, 5],
        "precipitation": [0, 0, 0, 0.02, 0.12, 0.05, 0, 0],
        "weather_code": [3, 3, 3, 61, 63, 61, 3, 2],
    }}


def test_game_window_takes_the_worst_hour_and_sums_rain():
    wx = game_window(_forecast(), datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc), 3.5)
    assert wx["temp_f"] == 64                        # kickoff hour
    assert wx["wind_mph"] == 18 and wx["wind_gust_mph"] == 34
    assert wx["precip_pct"] == 60
    assert wx["precip_in"] == 0.19 and wx["precip_max_in_hr"] == 0.12
    assert wx["weather_code"] == 63                  # rain outranks light rain


def test_game_window_outside_forecast_is_none():
    assert game_window(_forecast(), datetime(2026, 10, 5, 17, tzinfo=timezone.utc), 3.5) is None


def test_rain_desc_words():
    assert rain_desc(61, 0.05, 0.03, 31)["text"] == "Light rain, 0.05 in (31% chance)"
    assert rain_desc(82, 0.8, 0.5, 90)["label"] == "Downpours"
    assert rain_desc(61, 0.9, 0.45, 80)["label"] == "Heavy rain"     # amount outranks a mild code
    assert rain_desc(95, 0.01, 0.01, 50)["label"] == "Thunderstorms"  # a small amount never downgrades a storm
    assert rain_desc(3, 0, 0, 40)["text"] == "40% chance of rain, little expected"
    assert rain_desc(3, 0, 0, 10)["text"] is None
    assert rain_desc(None, 0.03, 0.01, 50)["label"] == "Sprinkles"   # older rows: amount only


def test_gusts_make_wind_strong_for_nfl():
    n = weather_note("nfl", 12, 31, 65, gust=29, rain=rain_desc(61, 0.05, 0.03, 31))
    assert n["tone"] == "warn" and n["tag"] == "WIND" and "gusts to 29" in n["why"]
    assert "Light rain: a small drag at most" in n["why"]


def test_heavy_rain_nfl_and_storm_mlb():
    assert weather_note("nfl", 5, 90, 60, rain=rain_desc(65, 0.6, 0.35, 90))["tag"] == "RAIN"
    assert weather_note("mlb", 3, 70, 75, rain=rain_desc(95, 0.3, 0.2, 70))["tag"] == "STORM"


def test_weather_text():
    t = weather_text({"temp_f": 65, "wind_mph": 12, "wind_dir": "NE", "wind_gust_mph": 29,
                      "precip_pct": 31, "rain": "Light rain, 0.05 in (31% chance)"})
    assert t == "65°F, wind 12 mph NE (gusts 29), light rain, 0.05 in (31% chance)"
