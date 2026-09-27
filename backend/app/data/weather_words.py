"""Plain-English rain descriptions for the weather forecast.

get_weather_forecast.py stores, per game, the most severe Open-Meteo WMO
weather code over the game window, the rain summed over the game
(precip_in), the wettest single hour (precip_max_in_hr) and the highest
chance of rain (precip_pct). rain_desc() turns those into a word people
use -- drizzle, light rain, downpours, thunderstorms -- and a severity the
pages use for colour and the briefing uses for its impact line.

Severity: 0 nothing expected, 1 light (sprinkles, drizzle, light rain,
scattered showers), 2 steady (rain, showers, light snow), 3 heavy (heavy
rain, downpours, thunderstorms, freezing rain, snow).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# WMO code -> (word, severity). Codes 0-3 (clear to overcast) and 45/48 (fog)
# carry no precipitation and aren't listed.
CODES = {
    51: ("Light drizzle", 1), 53: ("Drizzle", 1), 55: ("Heavy drizzle", 2),
    56: ("Freezing drizzle", 3), 57: ("Freezing drizzle", 3),
    61: ("Light rain", 1), 63: ("Rain", 2), 65: ("Heavy rain", 3),
    66: ("Freezing rain", 3), 67: ("Freezing rain", 3),
    71: ("Light snow", 2), 73: ("Snow", 3), 75: ("Heavy snow", 3), 77: ("Snow grains", 2),
    80: ("Scattered showers", 1), 81: ("Showers", 2), 82: ("Downpours", 3),
    85: ("Snow showers", 2), 86: ("Heavy snow showers", 3),
    95: ("Thunderstorms", 3), 96: ("Thunderstorms with hail", 3), 99: ("Thunderstorms with hail", 3),
}

# By rate alone (inches in the wettest hour), for rows written before the
# weather code was stored, or when the code and the amount disagree.
RATE_WORDS = ((0.30, "Heavy rain", 3), (0.10, "Rain", 2), (0.02, "Light rain", 1), (0.005, "Sprinkles", 1))


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def rain_desc(code: Any, precip_in: Any, max_rate: Any, pct: Any) -> Dict[str, Any]:
    """{"label", "severity", "text"} for one game. `text` is what the pages
    show, e.g. "Light rain, 0.05 in" or "40% chance, little expected";
    None when there's nothing worth saying. Pure, so it's tested directly."""
    code_n, total, rate, chance = _num(code), _num(precip_in), _num(max_rate), _num(pct)
    label, sev = None, 0
    if code_n is not None and int(code_n) in CODES:
        label, sev = CODES[int(code_n)]
    if rate is not None:
        for floor, word, s in RATE_WORDS:
            if rate >= floor:
                # The amount outranks a milder code ("Light rain" at 0.4 in/hr
                # is heavy rain); a milder amount never downgrades a storm.
                if s > sev:
                    label, sev = word, s
                break
    if label is None and (rate or 0) > 0:
        label, sev = "Sprinkles", 1
    amount = f"{total:.2f} in" if total and total >= 0.01 else None
    if label:
        text = label + (f", {amount}" if amount else "")
        if chance is not None and chance < 60:
            text += f" ({chance:.0f}% chance)"
        return {"label": label, "severity": sev, "text": text}
    if chance is not None and chance >= 30:
        # "little expected" only when we know the amount; an older forecast
        # row has only the chance.
        tail = ", little expected" if total is not None or code_n is not None else ""
        return {"label": None, "severity": 0, "text": f"{chance:.0f}% chance of rain{tail}"}
    return {"label": None, "severity": 0, "text": None}
