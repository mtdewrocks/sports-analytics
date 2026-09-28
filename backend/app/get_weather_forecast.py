"""Live wind/temp/precip FORECAST for upcoming MLB and NFL games (games that
haven't started yet).

Source, per venue:
  US venues  the National Weather Service's gridpoint forecast
             (api.weather.gov) -- US government data, free to use
             commercially, and the forecast most weather apps and TV
             stations show.
  elsewhere  MET Norway's Locationforecast (api.met.no) -- free for
             commercial use under CC BY 4.0 with credit ("Data from MET
             Norway", shown on the weather pages). Covers games abroad
             (London, Madrid, Rio, ...) and Toronto.
  Any field NWS leaves empty is filled from MET Norway, and a venue NWS
  can't answer for uses MET Norway entirely. `wx_source` says which one a
  row came from.

  Open-Meteo was the source until Sept 2026; its free API is
  non-commercial only (its terms name subscription websites), so it's no
  longer used.

This is a genuine forecast, unlike the two pages this replaces:
  - the old MLB Weather page was static ballpark trivia, no live data at all
  - the old NFL Weather page was a BACKTEST of already-played games' real
    recorded conditions, not a forecast for what hasn't happened yet

Run periodically through the day (see .github/workflows/update_weather.yml)
so a forecast that firms up between runs -- wind easing, a rain chance
dropping -- reaches the page within a couple of hours, for games still
in the future at run time. A game already underway or finished by the time
this runs is simply dropped from the output on the next pass; this file is a
snapshot of what's upcoming, not history.

    python backend/app/get_weather_forecast.py

Output:
  backend/data/mlb/mlb_weather_forecast.parquet
  backend/data/nfl/nfl_weather_forecast.parquet
(either may be skipped/empty if that sport has nothing upcoming right now --
e.g. an MLB off-day, or an NFL bye week with no games left on the slate the
forecast window covers.)
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

MLB_API = "https://statsapi.mlb.com/api/v1"
MET_API = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
# Same value as Settings.NFL_BASE_URL in app/config.py, duplicated here on
# purpose: this script runs as a bare `python backend/app/get_weather_
# forecast.py` from the repo root in CI (see .github/workflows/
# update_weather.yml), with no PYTHONPATH pointing at backend/, so `app` is
# not an importable package in that context -- importing app.config raises
# ModuleNotFoundError: No module named 'app'. Every sibling get_*.py script
# in this file avoids the same trap by staying self-contained rather than
# reaching into app.*, so this follows that convention instead of trying to
# special-case an import path for one script.
NFL_SCHEDULE_URL = "https://github.com/mtdewrocks/sports-analytics/releases/download/data-nfl/nfl_schedule.parquet"
TIMEOUT = 30

MLB_OUT = Path(__file__).resolve().parent.parent / "data" / "mlb" / "mlb_weather_forecast.parquet"
NFL_OUT = Path(__file__).resolve().parent.parent / "data" / "nfl" / "nfl_weather_forecast.parquet"

# nflverse's schedule times (`gametime`) are published in US/Eastern
# regardless of the stadium's actual local zone -- the standard "1:00 PM
# ET" / "4:25 PM ET" / "8:15 PM ET" windows the NFL itself publishes in.
NFL_SCHEDULE_TZ = ZoneInfo("America/New_York")

NWS_API = "https://api.weather.gov"
# NWS asks every client to identify itself with a contact.
NWS_HEADERS = {"User-Agent": "sports-analytics (github.com/mtdewrocks/sports-analytics)",
               "Accept": "application/geo+json"}

# NWS "weather" entries -> the WMO codes the rest of this file speaks, by
# (weather, intensity). Intensity: very_light/light -> first, moderate ->
# second, heavy -> third. The amount decides the final word anyway
# (app/data/weather_words.py); this mainly carries the KIND of weather.
_NWS_CODES = {
    "drizzle": (51, 53, 55), "rain": (61, 63, 65), "rain_showers": (80, 81, 82),
    "thunderstorms": (95, 95, 95), "snow": (71, 73, 75), "snow_showers": (85, 85, 86),
    "freezing_rain": (66, 66, 67), "freezing_drizzle": (56, 56, 57), "sleet": (66, 66, 67),
    "fog": (45, 45, 45),
}
_NWS_LEVEL = {"very_light": 0, "light": 0, "moderate": 1, "heavy": 2}

# How long a game runs, for the forecast window: wind, gusts and rain chance
# are the worst hour from first pitch / kickoff to this many hours later, and
# rain amounts are summed over it. The start hour alone missed weather that
# arrives mid-game.
GAME_HOURS = {"mlb": 3.0, "nfl": 3.5}

# WMO weather codes, ranked by how much they matter to a game --
# the window's most severe code is the one reported.
_CODE_RANK = {0: 0, 1: 0, 2: 0, 3: 0, 45: 1, 48: 1,
              51: 2, 53: 3, 55: 4, 56: 5, 57: 6,
              61: 3, 63: 5, 65: 7, 66: 6, 67: 8,
              71: 5, 73: 6, 75: 8, 77: 5,
              80: 4, 81: 6, 82: 8, 85: 6, 86: 8,
              95: 9, 96: 10, 99: 10}
_EMPTY_WX = {"temp_f": None, "wind_mph": None, "wind_gust_mph": None, "wind_dir_deg": None,
             "precip_pct": None, "precip_in": None, "precip_max_in_hr": None, "weather_code": None,
             "wx_source": None}

# ---------------------------------------------------------------------------
# Stadium coordinates. Approximate (city-block accuracy) is plenty for an
# hourly weather forecast -- these aren't survey coordinates.
#
# roof: "outdoor" (always weather-exposed), "retractable" (weather-exposed
# when open -- which is most MLB retractable parks most of the time, but NOT
# most NFL ones -- included anyway with the tag so the page can label it
# rather than silently guess), or "dome" (fixed roof, no plausible weather
# exposure -- included in the output so the page can show "indoors", not
# fetched at all since there's nothing to forecast).
# ---------------------------------------------------------------------------

MLB_STADIUMS: dict[str, dict] = {
    "Arizona Diamondbacks":  {"lat": 33.4455, "lon": -112.0667, "stadium": "Chase Field",                 "roof": "retractable"},
    "Atlanta Braves":        {"lat": 33.8908, "lon": -84.4678,  "stadium": "Truist Park",                 "roof": "outdoor"},
    "Baltimore Orioles":     {"lat": 39.2839, "lon": -76.6218,  "stadium": "Oriole Park at Camden Yards",  "roof": "outdoor"},
    "Boston Red Sox":        {"lat": 42.3467, "lon": -71.0972,  "stadium": "Fenway Park",                  "roof": "outdoor"},
    "Chicago Cubs":          {"lat": 41.9484, "lon": -87.6553,  "stadium": "Wrigley Field",                "roof": "outdoor"},
    "Chicago White Sox":     {"lat": 41.8299, "lon": -87.6338,  "stadium": "Rate Field",                   "roof": "outdoor"},
    "Cincinnati Reds":       {"lat": 39.0979, "lon": -84.5066,  "stadium": "Great American Ball Park",     "roof": "outdoor"},
    "Cleveland Guardians":   {"lat": 41.4962, "lon": -81.6852,  "stadium": "Progressive Field",            "roof": "outdoor"},
    "Colorado Rockies":      {"lat": 39.7559, "lon": -104.9942, "stadium": "Coors Field",                  "roof": "outdoor"},
    "Detroit Tigers":        {"lat": 42.3390, "lon": -83.0485,  "stadium": "Comerica Park",                "roof": "outdoor"},
    "Houston Astros":        {"lat": 29.7573, "lon": -95.3555,  "stadium": "Daikin Park",                  "roof": "retractable"},
    "Kansas City Royals":    {"lat": 39.0517, "lon": -94.4803,  "stadium": "Kauffman Stadium",             "roof": "outdoor"},
    "Los Angeles Angels":    {"lat": 33.8003, "lon": -117.8827, "stadium": "Angel Stadium",                "roof": "outdoor"},
    "Los Angeles Dodgers":   {"lat": 34.0739, "lon": -118.2400, "stadium": "Dodger Stadium",               "roof": "outdoor"},
    "Miami Marlins":         {"lat": 25.7781, "lon": -80.2196,  "stadium": "loanDepot park",               "roof": "retractable"},
    "Milwaukee Brewers":     {"lat": 43.0280, "lon": -87.9712,  "stadium": "American Family Field",        "roof": "retractable"},
    "Minnesota Twins":       {"lat": 44.9817, "lon": -93.2776,  "stadium": "Target Field",                 "roof": "outdoor"},
    "New York Mets":         {"lat": 40.7571, "lon": -73.8458,  "stadium": "Citi Field",                   "roof": "outdoor"},
    "New York Yankees":      {"lat": 40.8296, "lon": -73.9262,  "stadium": "Yankee Stadium",               "roof": "outdoor"},
    "Athletics":             {"lat": 38.5802, "lon": -121.5133, "stadium": "Sutter Health Park",           "roof": "outdoor"},
    "Philadelphia Phillies": {"lat": 39.9061, "lon": -75.1665,  "stadium": "Citizens Bank Park",           "roof": "outdoor"},
    "Pittsburgh Pirates":    {"lat": 40.4469, "lon": -80.0057,  "stadium": "PNC Park",                     "roof": "outdoor"},
    "San Diego Padres":      {"lat": 32.7073, "lon": -117.1566, "stadium": "Petco Park",                   "roof": "outdoor"},
    "Seattle Mariners":      {"lat": 47.5914, "lon": -122.3325, "stadium": "T-Mobile Park",                "roof": "retractable"},
    "San Francisco Giants":  {"lat": 37.7786, "lon": -122.3893, "stadium": "Oracle Park",                  "roof": "outdoor"},
    "St. Louis Cardinals":   {"lat": 38.6226, "lon": -90.1928,  "stadium": "Busch Stadium",                "roof": "outdoor"},
    "Tampa Bay Rays":        {"lat": 27.7683, "lon": -82.6534,  "stadium": "Tropicana Field",              "roof": "dome"},
    "Texas Rangers":         {"lat": 32.7473, "lon": -97.0828,  "stadium": "Globe Life Field",             "roof": "retractable"},
    "Toronto Blue Jays":     {"lat": 43.6414, "lon": -79.3894,  "stadium": "Rogers Centre",                "roof": "retractable"},
    "Washington Nationals":  {"lat": 38.8730, "lon": -77.0074,  "stadium": "Nationals Park",               "roof": "outdoor"},
}

# Keyed by the exact 'stadium' string nfl_schedule.parquet uses -- that file
# already carries a per-game venue (and covers relocations/international
# games on its own), so this only needs to add coordinates + a static roof
# classification, not a team -> venue mapping of its own.
NFL_STADIUMS: dict[str, dict] = {
    "State Farm Stadium":              {"lat": 33.5276, "lon": -112.2626, "roof": "retractable"},
    "Mercedes-Benz Stadium":           {"lat": 33.7554, "lon": -84.4008,  "roof": "retractable"},
    "M&T Bank Stadium":                {"lat": 39.2780, "lon": -76.6227,  "roof": "outdoor"},
    "Highmark Stadium":                {"lat": 42.7738, "lon": -78.7870,  "roof": "outdoor"},
    "Bank of America Stadium":         {"lat": 35.2258, "lon": -80.8528,  "roof": "outdoor"},
    "Soldier Field":                   {"lat": 41.8623, "lon": -87.6167,  "roof": "outdoor"},
    "Paycor Stadium":                  {"lat": 39.0955, "lon": -84.5160,  "roof": "outdoor"},
    "Huntington Bank Field":           {"lat": 41.5061, "lon": -81.6995,  "roof": "outdoor"},
    "AT&T Stadium":                    {"lat": 32.7473, "lon": -97.0945,  "roof": "retractable"},
    "Empower Field at Mile High":      {"lat": 39.7439, "lon": -105.0201, "roof": "outdoor"},
    "Ford Field":                      {"lat": 42.3400, "lon": -83.0456,  "roof": "dome"},
    "Lambeau Field":                   {"lat": 44.5013, "lon": -88.0622,  "roof": "outdoor"},
    "Reliant Stadium":                 {"lat": 29.6847, "lon": -95.4107,  "roof": "retractable"},
    "NRG Stadium":                     {"lat": 29.6847, "lon": -95.4107,  "roof": "retractable"},
    "Lucas Oil Stadium":               {"lat": 39.7601, "lon": -86.1639,  "roof": "retractable"},
    "EverBank Stadium":                {"lat": 30.3239, "lon": -81.6373,  "roof": "outdoor"},
    "GEHA Field at Arrowhead Stadium": {"lat": 39.0489, "lon": -94.4839,  "roof": "outdoor"},
    "SoFi Stadium":                    {"lat": 33.9535, "lon": -118.3392, "roof": "dome"},
    "Allegiant Stadium":               {"lat": 36.0909, "lon": -115.1833, "roof": "dome"},
    "Hard Rock Stadium":               {"lat": 25.9580, "lon": -80.2389,  "roof": "outdoor"},
    "U.S. Bank Stadium":               {"lat": 44.9736, "lon": -93.2575,  "roof": "dome"},
    "Gillette Stadium":                {"lat": 42.0909, "lon": -71.2643,  "roof": "outdoor"},
    "Caesars Superdome":               {"lat": 29.9511, "lon": -90.0812,  "roof": "dome"},
    "MetLife Stadium":                 {"lat": 40.8135, "lon": -74.0745,  "roof": "outdoor"},
    "Lincoln Financial Field":         {"lat": 39.9008, "lon": -75.1675,  "roof": "outdoor"},
    "Acrisure Stadium":                {"lat": 40.4468, "lon": -80.0158,  "roof": "outdoor"},
    "Lumen Field":                     {"lat": 47.5952, "lon": -122.3316, "roof": "outdoor"},
    "Levi's Stadium":                  {"lat": 37.4032, "lon": -121.9698, "roof": "outdoor"},
    "Raymond James Stadium":           {"lat": 27.9759, "lon": -82.5033,  "roof": "outdoor"},
    "Nissan Stadium":                  {"lat": 36.1665, "lon": -86.7713,  "roof": "outdoor"},
    "Northwest Stadium":               {"lat": 38.9078, "lon": -76.8645,  "roof": "outdoor"},
    # International Series venues -- open-air soccer/cricket grounds, no
    # roof to speak of, included so a London/Madrid/Munich/Rio/Melbourne
    # game still gets a real forecast instead of silently vanishing from
    # the page just because it's not a US venue.
    "Wembley Stadium":                 {"lat": 51.5560, "lon": -0.2795,   "roof": "outdoor"},
    "Tottenham Hotspur Stadium":       {"lat": 51.6043, "lon": -0.0664,   "roof": "outdoor"},
    "Bernabeu":                        {"lat": 40.4531, "lon": -3.6883,   "roof": "outdoor"},
    "Estadio Santiago Bernabeu":       {"lat": 40.4531, "lon": -3.6883,   "roof": "outdoor"},
    "Allianz Arena":                   {"lat": 48.2188, "lon": 11.6247,   "roof": "outdoor"},
    "FC Bayern Munich Stadium":        {"lat": 48.2188, "lon": 11.6247,   "roof": "outdoor"},
    "Estadio Banorte":                 {"lat": 25.6689, "lon": -100.2434, "roof": "outdoor"},
    "Maracana Stadium":                {"lat": -22.9122, "lon": -43.2302, "roof": "outdoor"},
    "Stade de France":                 {"lat": 48.9244, "lon": 2.3601,    "roof": "outdoor"},
    "Melbourne Cricket Ground":        {"lat": -37.8199, "lon": 144.9834, "roof": "outdoor"},
}


def _met_code(symbol: str | None) -> int | None:
    """MET Norway symbol_code ("lightrainshowers_day", "heavyrainandthunder")
    -> the WMO code the rest of this file speaks."""
    if not symbol:
        return None
    s = symbol.split("_")[0]
    if "thunder" in s:
        return 95
    heavy, light = s.startswith("heavy"), s.startswith("light")
    level = 2 if heavy else (0 if light else 1)
    if "sleet" in s:
        return 66
    if "snowshowers" in s:
        return (85, 85, 86)[level]
    if "snow" in s:
        return (71, 73, 75)[level]
    if "rainshowers" in s:
        return (80, 81, 82)[level]
    if "rain" in s:
        return (61, 63, 65)[level]
    if s == "fog":
        return 45
    return {"clearsky": 0, "fair": 1, "partlycloudy": 2, "cloudy": 3}.get(s)


def met_to_hourly(payload: dict) -> dict:
    """MET Norway Locationforecast JSON -> a standard hourly
    {"hourly": {...}} for game_window(). Pure, so it's tested directly.

    Each timeseries step carries instant values (temperature, wind, gusts,
    direction) and the next 1 (or, further out, 6) hours' precipitation,
    chance and symbol. Amounts are keyed to the END of their period, like
    the other sources; a 6-hour amount is spread evenly. Units: degC -> F,
    m/s -> mph, mm -> in."""
    times, temp, wind, gust, wdir, pop, precip, code = [], [], [], [], [], [], [], []
    extra: dict = {}
    for step in (payload.get("properties") or {}).get("timeseries") or []:
        try:
            t = datetime.fromisoformat(step["time"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        data = step.get("data") or {}
        inst = (data.get("instant") or {}).get("details") or {}
        nxt, n = data.get("next_1_hours"), 1
        if not nxt:
            nxt, n = data.get("next_6_hours"), 6
        nd = (nxt or {}).get("details") or {}
        times.append(t)
        temp.append(None if inst.get("air_temperature") is None else round(inst["air_temperature"] * 9 / 5 + 32, 1))
        wind.append(None if inst.get("wind_speed") is None else round(inst["wind_speed"] * 2.23694, 1))
        gust.append(None if inst.get("wind_speed_of_gust") is None else round(inst["wind_speed_of_gust"] * 2.23694, 1))
        wdir.append(inst.get("wind_from_direction"))
        pop.append(nd.get("probability_of_precipitation"))
        code.append(_met_code(((nxt or {}).get("summary") or {}).get("symbol_code")))
        amt = nd.get("precipitation_amount")
        if amt is not None:
            per = amt / 25.4 / n
            for h in range(1, n + 1):
                extra[t + timedelta(hours=h)] = extra.get(t + timedelta(hours=h), 0) + round(per, 3)
    for t in extra:
        if t not in times:
            times.append(t)
            for col in (temp, wind, gust, wdir, pop, code):
                col.append(None)
    order = sorted(range(len(times)), key=lambda i: times[i])
    pick = lambda col: [col[i] for i in order]  # noqa: E731
    ts = [times[i] for i in order]
    return {"hourly": {
        "time": [t.isoformat(timespec="minutes") for t in ts],
        "temperature_2m": pick(temp), "wind_speed_10m": pick(wind), "wind_gusts_10m": pick(gust),
        "wind_direction_10m": pick(wdir), "precipitation_probability": pick(pop),
        "precipitation": [extra.get(t) for t in ts], "weather_code": pick(code),
    }}


_MET_CACHE: dict = {}


def _fetch_met(lat: float, lon: float) -> dict | None:
    """MET Norway's forecast for one venue, or None if it can't answer."""
    key = (round(lat, 4), round(lon, 4))
    if key in _MET_CACHE:
        return _MET_CACHE[key]
    out = None
    try:
        r = requests.get(MET_API, params={"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"},
                         headers={"User-Agent": NWS_HEADERS["User-Agent"]}, timeout=TIMEOUT)
        if r.status_code == 200:
            out = met_to_hourly(r.json())
        else:
            print(f"warning: MET Norway {lat},{lon}: HTTP {r.status_code}")
    except (requests.RequestException, ValueError) as e:
        print(f"warning: MET Norway forecast for {lat},{lon} failed: {e}")
    _MET_CACHE[key] = out
    return out


def venue_window(lat: float, lon: float, start_utc: datetime, hours: float) -> dict | None:
    """The game window for one venue: NWS first; MET Norway only when NWS
    has nothing or leaves a field empty (so US games cost one call)."""
    nws = _fetch_nws(lat, lon)
    first = game_window(nws, start_utc, hours) if nws else None
    if first is not None and all(v is not None for v in first.values()):
        return {**first, "wx_source": "nws"}
    return best_window(nws, _fetch_met(lat, lon), start_utc, hours)


def _iso_duration_hours(d: str) -> int:
    """"PT3H" -> 3, "P1DT6H" -> 30 (NWS validTime durations)."""
    import re
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", d)
    if not m:
        return 1
    days, hours = int(m.group(1) or 0), int(m.group(2) or 0)
    return max(1, days * 24 + hours)


def nws_to_hourly(props: dict) -> dict:
    """NWS gridpoint properties -> a standard hourly {"hourly": {...}}
    so game_window() reads both sources the same way. Pure, so it's tested
    directly.

    Each NWS series is [{validTime: "2026-09-27T17:00:00+00:00/PT3H",
    value}], a value held over a span. Spans are spread to hours; the
    rain amount (quantitativePrecipitation, a total per span) is divided
    evenly across its hours. Units: degC -> F, km/h -> mph, mm -> in.
    A field NWS doesn't give stays None for that hour."""
    def expand(name: str, conv=lambda v: v, split: bool = False) -> dict:
        out = {}
        for item in (props.get(name) or {}).get("values") or []:
            start_s, _, dur = str(item.get("validTime", "")).partition("/")
            try:
                start = datetime.fromisoformat(start_s).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
            n = _iso_duration_hours(dur or "PT1H")
            val = item.get("value")
            for h in range(n):
                # Amounts are keyed to the END of their hour, matching
                # MET Norway's and the old source's "total for the
                # preceding hour".
                t = start + timedelta(hours=h + (1 if split else 0))
                if name == "weather":
                    out[t] = val
                else:
                    out[t] = None if val is None else conv(val / n if split else val)
        return out

    def weather_code(entries) -> int | None:
        best, best_rank = None, -1
        for e in entries or []:
            kind = (e or {}).get("weather")
            if kind not in _NWS_CODES:
                continue
            code = _NWS_CODES[kind][_NWS_LEVEL.get((e or {}).get("intensity") or "light", 0)]
            if _CODE_RANK.get(code, 0) > best_rank:
                best, best_rank = code, _CODE_RANK.get(code, 0)
        return best

    temp = expand("temperature", lambda c: round(c * 9 / 5 + 32, 1))
    wind = expand("windSpeed", lambda k: round(k * 0.621371, 1))
    gust = expand("windGust", lambda k: round(k * 0.621371, 1))
    wdir = expand("windDirection")
    pop = expand("probabilityOfPrecipitation")
    qpf = expand("quantitativePrecipitation", lambda mm: round(mm / 25.4, 3), split=True)
    wx = expand("weather")
    times = sorted(set(temp) | set(wind) | set(pop) | set(qpf))
    return {"hourly": {
        "time": [t.isoformat(timespec="minutes") for t in times],
        "temperature_2m": [temp.get(t) for t in times],
        "wind_speed_10m": [wind.get(t) for t in times],
        "wind_gusts_10m": [gust.get(t) for t in times],
        "wind_direction_10m": [wdir.get(t) for t in times],
        "precipitation_probability": [pop.get(t) for t in times],
        "precipitation": [qpf.get(t) for t in times],
        "weather_code": [weather_code(wx.get(t)) for t in times],
    }}


_NWS_GRID_CACHE: dict = {}


def _fetch_nws(lat: float, lon: float) -> dict | None:
    """The NWS gridpoint forecast for one venue, standard hourly, or None
    when NWS can't answer (outside the US, or the service is down)."""
    key = (round(lat, 4), round(lon, 4))
    if key in _NWS_GRID_CACHE:
        return _NWS_GRID_CACHE[key]
    out = None
    try:
        pt = requests.get(f"{NWS_API}/points/{lat:.4f},{lon:.4f}", headers=NWS_HEADERS, timeout=TIMEOUT)
        if pt.status_code == 200:
            grid_url = pt.json()["properties"]["forecastGridData"]
            gr = requests.get(grid_url, headers=NWS_HEADERS, timeout=TIMEOUT)
            if gr.status_code == 200:
                out = nws_to_hourly(gr.json()["properties"])
    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"warning: NWS forecast for {lat},{lon} failed: {e}")
    _NWS_GRID_CACHE[key] = out
    return out


def best_window(nws: dict | None, fallback: dict | None, start_utc: datetime, hours: float) -> dict | None:
    """NWS's game window, with any field it lacks filled from the fallback
    (MET Norway); the fallback alone when NWS has nothing. Adds `wx_source`."""
    a = game_window(nws, start_utc, hours) if nws else None
    b = game_window(fallback, start_utc, hours) if fallback else None
    if a is None and b is None:
        return None
    if a is None:
        return {**b, "wx_source": "met-norway"}
    filled = {k: (v if v is not None else (b or {}).get(k)) for k, v in a.items()}
    return {**filled, "wx_source": "nws"}


def game_window(forecast: dict, start_utc: datetime, hours: float) -> dict | None:
    """Weather over a game, from one location's hourly forecast. Pure, so
    it's tested directly.

    temp and wind direction: the hour nearest the start.
    wind, gusts, rain chance, weather code: the worst hour from the start
    hour through `hours` later (the code by _CODE_RANK severity).
    precip_in: rain summed over the game. Each hourly precipitation value
    is the total for the PRECEDING hour, so the hours after the start through
    the end are summed. precip_max_in_hr: the wettest of those hours.

    None when the start falls outside the forecast (more than 90 minutes
    from any hourly point), rather than fabricating a match."""
    hourly = forecast.get("hourly") or {}
    times = [datetime.fromisoformat(t) for t in (hourly.get("time") or [])]
    if not times:
        return None
    start = start_utc.replace(tzinfo=None)
    near = min(range(len(times)), key=lambda i: abs((times[i] - start).total_seconds()))
    if abs((times[near] - start).total_seconds()) > 90 * 60:
        return None
    end = start + timedelta(hours=hours)
    first = start.replace(minute=0, second=0, microsecond=0)
    during = [i for i, t in enumerate(times) if first <= t <= end]
    rained = [i for i, t in enumerate(times) if start < t <= end + timedelta(minutes=59)]

    def col(name: str) -> list:
        return hourly.get(name) or [None] * len(times)

    def worst(name: str, idx: list) -> float | None:
        vals = [v for v in (col(name)[i] for i in idx) if v is not None]
        return max(vals) if vals else None

    precip = [v for v in (col("precipitation")[i] for i in rained) if v is not None]
    codes = [c for c in (col("weather_code")[i] for i in during) if c is not None]
    return {
        "temp_f": col("temperature_2m")[near],
        "wind_mph": worst("wind_speed_10m", during),
        "wind_gust_mph": worst("wind_gusts_10m", during),
        "wind_dir_deg": col("wind_direction_10m")[near],
        "precip_pct": worst("precipitation_probability", during),
        "precip_in": round(sum(precip), 2) if precip else None,
        "precip_max_in_hr": round(max(precip), 2) if precip else None,
        "weather_code": max(codes, key=lambda c: _CODE_RANK.get(int(c), 0)) if codes else None,
    }


def _mlb_upcoming_games() -> pd.DataFrame:
    """Today's MLB slate with each game's actual start time -- same MLB
    Stats API endpoint get_probable_starters.py already uses, kept
    independent of that script's output on purpose (self-contained, no
    ordering dependency between builders in the workflow)."""
    day = datetime.now(timezone.utc).date().isoformat()
    r = requests.get(f"{MLB_API}/schedule", params={"sportId": 1, "date": day}, timeout=TIMEOUT)
    r.raise_for_status()
    games = [g for d in r.json().get("dates", []) for g in d["games"]]

    now = datetime.now(timezone.utc)
    rows = []
    for g in games:
        # abstractGameState is "Preview" before first pitch, "Live" during,
        # "Final" after -- only forecast games that haven't started.
        if g.get("status", {}).get("abstractGameState") != "Preview":
            continue
        home = g["teams"]["home"]["team"]["name"]
        away = g["teams"]["away"]["team"]["name"]
        game_time = g.get("gameDate")  # ISO8601 UTC, e.g. "2026-09-21T23:10:00Z"
        if not game_time:
            continue
        start = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
        if start < now:
            continue
        rows.append({
            "game_pk": g["gamePk"], "home_team": home, "away_team": away,
            "game_time_utc": start,
        })
    return pd.DataFrame(rows)


def _nfl_upcoming_games() -> pd.DataFrame:
    """Every scheduled-but-not-yet-played NFL game currently on the
    published schedule (this season, kickoff still in the future) -- not
    just this week's, so a Thursday run already has next Sunday's slate
    ready rather than waiting for the week to turn over."""
    r = requests.get(NFL_SCHEDULE_URL, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_parquet(io.BytesIO(r.content))

    now = datetime.now(timezone.utc)
    season = df["season"].max()
    df = df[(df["season"] == season) & df["gameday"].notna() & df["gametime"].notna()].copy()

    def _kickoff_utc(row) -> datetime | None:
        try:
            d = pd.to_datetime(row["gameday"]).date()
            h, m = str(row["gametime"]).split(":")[:2]
            local = datetime(d.year, d.month, d.day, int(h), int(m), tzinfo=NFL_SCHEDULE_TZ)
            return local.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    df["kickoff_utc"] = df.apply(_kickoff_utc, axis=1)
    df = df[df["kickoff_utc"].notna() & (df["kickoff_utc"] > now)]
    # Already-played games (this season, still technically "future" by date
    # if the score hasn't posted yet for some data-lag reason) are excluded
    # by the score check too, belt-and-suspenders with the kickoff-time
    # filter above.
    df = df[df["home_score"].isna()]
    return df[["game_id", "week", "gameday", "gametime", "home_team", "away_team", "stadium", "kickoff_utc"]]


def build_mlb() -> pd.DataFrame:
    games = _mlb_upcoming_games()
    if games.empty:
        return games

    venues = []
    for _, g in games.iterrows():
        info = MLB_STADIUMS.get(g["home_team"])
        if info is None:
            print(f"warning: no stadium entry for MLB team '{g['home_team']}' -- skipping")
            continue
        venues.append((g, info))

    to_fetch = [(g, info) for g, info in venues if info["roof"] != "dome"]
    rows = []
    for g, info in to_fetch:
        wx = venue_window(info["lat"], info["lon"], g["game_time_utc"], GAME_HOURS["mlb"])
        rows.append({
            "game_pk": g["game_pk"], "home_team": g["home_team"], "away_team": g["away_team"],
            "stadium": info["stadium"], "roof": info["roof"],
            "game_time_utc": g["game_time_utc"].isoformat(),
            **(wx or _EMPTY_WX),
        })
    # Dome games -- no forecast fetched, but still listed so the page can
    # show "Indoors" instead of the game silently not appearing at all.
    for g, info in venues:
        if info["roof"] == "dome":
            rows.append({
                "game_pk": g["game_pk"], "home_team": g["home_team"], "away_team": g["away_team"],
                "stadium": info["stadium"], "roof": info["roof"],
                "game_time_utc": g["game_time_utc"].isoformat(),
                **_EMPTY_WX,
            })
    return pd.DataFrame(rows)


def build_nfl() -> pd.DataFrame:
    games = _nfl_upcoming_games()
    if games.empty:
        return games

    venues = []
    for _, g in games.iterrows():
        info = NFL_STADIUMS.get(g["stadium"])
        if info is None:
            print(f"warning: no stadium entry for NFL venue '{g['stadium']}' -- skipping")
            continue
        venues.append((g, info))

    to_fetch = [(g, info) for g, info in venues if info["roof"] != "dome"]
    rows = []
    for g, info in to_fetch:
        wx = venue_window(info["lat"], info["lon"], g["kickoff_utc"], GAME_HOURS["nfl"])
        rows.append({
            "game_id": g["game_id"], "week": int(g["week"]), "home_team": g["home_team"], "away_team": g["away_team"],
            "stadium": g["stadium"], "roof": info["roof"], "kickoff_utc": g["kickoff_utc"].isoformat(),
            **(wx or _EMPTY_WX),
        })
    for g, info in venues:
        if info["roof"] == "dome":
            rows.append({
                "game_id": g["game_id"], "week": int(g["week"]), "home_team": g["home_team"], "away_team": g["away_team"],
                "stadium": g["stadium"], "roof": info["roof"], "kickoff_utc": g["kickoff_utc"].isoformat(),
                **_EMPTY_WX,
            })
    return pd.DataFrame(rows)


def main() -> None:
    mlb = build_mlb()
    MLB_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not mlb.empty:
        mlb.to_parquet(MLB_OUT, index=False)
        print(f"{len(mlb)} upcoming MLB game(s) -> {MLB_OUT}")
    else:
        print("No upcoming (not-yet-started) MLB games right now -- leaving any existing file untouched")

    nfl = build_nfl()
    NFL_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not nfl.empty:
        nfl.to_parquet(NFL_OUT, index=False)
        print(f"{len(nfl)} upcoming NFL game(s) -> {NFL_OUT}")
    else:
        print("No upcoming (not-yet-started) NFL games right now -- leaving any existing file untouched")


if __name__ == "__main__":
    main()
