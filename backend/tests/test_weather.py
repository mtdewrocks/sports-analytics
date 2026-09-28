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
    assert rain_desc(61, 0.9, 0.45, 80)["label"] == "Heavy rain"     # the amount sets how heavy
    assert rain_desc(95, 0.01, 0.01, 50)["label"] == "Thunderstorms"  # storms stay storms
    assert rain_desc(3, 0, 0, 40)["text"] == "40% chance of rain, little expected"
    assert rain_desc(3, 0, 0, 10)["text"] is None
    assert rain_desc(None, 0.03, 0.02, 50)["label"] == "Light rain"  # an amount with no precip code


def test_rain_desc_code_intensity_never_contradicts_the_amount():
    # Mets @ Nationals: code 55 ("dense drizzle") on 0.02 in -- was "Heavy drizzle".
    d = rain_desc(55, 0.02, 0.02, 45)
    assert d["text"] == "Drizzle, 0.02 in (45% chance)" and d["severity"] == 1
    assert rain_desc(61, 0.004, 0.004, 30)["label"] == "Sprinkles"
    assert rain_desc(53, 0.4, 0.2, 90)["label"] == "Rain"            # a lot of "drizzle" is rain
    assert rain_desc(63, None, None, 50)["label"] == "Rain"          # older rows: the code's intensity


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


def _nws_props():
    def series(*items):
        return {"values": [{"validTime": t, "value": v} for t, v in items]}
    return {
        "temperature": series(("2026-09-27T17:00:00+00:00/PT4H", 16.7)),
        "windSpeed": series(("2026-09-27T17:00:00+00:00/PT2H", 29.0), ("2026-09-27T19:00:00+00:00/PT2H", 32.0)),
        "windGust": series(("2026-09-27T17:00:00+00:00/PT4H", 66.0)),
        "windDirection": series(("2026-09-27T17:00:00+00:00/PT4H", 0)),
        "probabilityOfPrecipitation": series(("2026-09-27T17:00:00+00:00/PT1H", 83),
                                             ("2026-09-27T18:00:00+00:00/PT3H", 88)),
        "quantitativePrecipitation": series(("2026-09-27T12:00:00+00:00/PT6H", 3.0),
                                            ("2026-09-27T18:00:00+00:00/PT6H", 9.0)),
        "weather": {"values": [{"validTime": "2026-09-27T17:00:00+00:00/PT4H",
                                "value": [{"coverage": "likely", "weather": "rain_showers", "intensity": "moderate"}]}]},
    }


def test_nws_game_window_matches_the_forecast_people_see():
    from app.get_weather_forecast import nws_to_hourly
    wx = game_window(nws_to_hourly(_nws_props()), datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc), 3.5)
    assert wx["temp_f"] == 62.1
    assert round(wx["wind_mph"]) == 20 and round(wx["wind_gust_mph"]) == 41
    assert wx["precip_pct"] == 88
    assert wx["weather_code"] == 81
    # 3 mm over 12-18z and 9 mm over 18-24z, spread per hour, summed over 17z-21:30z
    assert wx["precip_in"] == 0.2    # 0.5 mm (17-18z) + 3 x 1.5 mm (18-21z)


def test_best_window_prefers_nws_and_fills_gaps():
    from app.get_weather_forecast import best_window, nws_to_hourly
    props = _nws_props(); props.pop("windGust")
    start = datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc)
    wx = best_window(nws_to_hourly(props), _forecast(), start, 3.5)
    assert wx["wx_source"] == "nws" and wx["precip_pct"] == 88
    assert wx["wind_gust_mph"] == 34                     # from the fallback
    assert best_window(None, _forecast(), start, 3.5)["wx_source"] == "met-norway"


def test_met_norway_to_hourly():
    from app.get_weather_forecast import met_to_hourly
    payload = {"properties": {"timeseries": [
        {"time": "2026-09-27T17:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 16.7, "wind_speed": 8.0, "wind_speed_of_gust": 18.3,
                                    "wind_from_direction": 10}},
            "next_1_hours": {"summary": {"symbol_code": "rainshowers_day"},
                             "details": {"precipitation_amount": 2.54, "probability_of_precipitation": 88}}}},
        {"time": "2026-09-27T18:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 16.0, "wind_speed": 9.0, "wind_speed_of_gust": 17.0,
                                    "wind_from_direction": 20}},
            "next_1_hours": {"summary": {"symbol_code": "heavyrainandthunder"},
                             "details": {"precipitation_amount": 10.16, "probability_of_precipitation": 90}}}},
    ]}}
    wx = game_window(met_to_hourly(payload), datetime(2026, 9, 27, 17, 0, tzinfo=timezone.utc), 2)
    assert wx["temp_f"] == 62.1
    assert round(wx["wind_mph"]) == 20 and round(wx["wind_gust_mph"]) == 41
    assert wx["precip_pct"] == 90 and wx["weather_code"] == 95
    assert wx["precip_in"] == 0.5                        # 0.1 in (17-18z) + 0.4 in (18-19z)


def test_carry_forward_keeps_kicked_off_games_for_the_week():
    import pandas as pd
    from app.get_weather_forecast import carry_forward
    now = datetime(2026, 9, 28, 18, tzinfo=timezone.utc)
    new = pd.DataFrame([{"game_id": "wk4_a", "kickoff_utc": "2026-10-04T17:00:00+00:00", "wind_mph": 5}])
    prev = pd.DataFrame([
        {"game_id": "wk3_sun", "kickoff_utc": "2026-09-27T17:00:00+00:00", "wind_mph": 18},   # kept
        {"game_id": "wk2_old", "kickoff_utc": "2026-09-20T17:00:00+00:00", "wind_mph": 9},    # too old
        {"game_id": "wk4_a", "kickoff_utc": "2026-10-04T17:00:00+00:00", "wind_mph": 3},      # replaced by new
    ])
    out = carry_forward(new, prev, now).set_index("game_id")
    assert set(out.index) == {"wk4_a", "wk3_sun"}
    assert out.loc["wk3_sun", "final"] and not out.loc["wk4_a", "final"]
    assert out.loc["wk4_a", "wind_mph"] == 5
