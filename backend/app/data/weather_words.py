"""Plain-English rain descriptions for the weather forecast.

get_weather_forecast.py stores, per game, the most severe Open-Meteo WMO
weather code over the game window, the rain summed over the game
(precip_in), the wettest single hour (precip_max_in_hr) and the highest
chance of rain (precip_pct). rain_desc() turns those into a word people
use -- drizzle, light rain, downpours, thunderstorms -- and a severity the
pages use for colour and the briefing uses for its impact line.

Severity: 0 nothing or a trace (sprinkles), 1 light (drizzle, light rain,
scattered showers), 2 steady (rain, showers, light snow), 3 heavy (heavy
rain, downpours, thunderstorms, freezing rain, snow).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# WMO code -> kind of precipitation. The code only says WHAT falls; how
# hard it falls comes from the forecast amount (INTENSITY below). The model's
# intensity in the code ("dense drizzle", code 55) can sit on a trivial
# amount -- 0.02 in over a game -- and "heavy drizzle" next to that reads as
# a contradiction.
KIND = {51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "freezing", 57: "freezing",
        61: "rain", 63: "rain", 65: "rain", 66: "freezing", 67: "freezing",
        71: "snow", 73: "snow", 75: "snow", 77: "snow",
        80: "showers", 81: "showers", 82: "showers", 85: "snow", 86: "snow",
        95: "storm", 96: "storm", 99: "storm"}

# Intensity from the wettest hour (inches of liquid): (floor, level).
# Roughly the NWS bands -- light under 0.10 in/hr, moderate to 0.30, heavy above.
INTENSITY = ((0.30, 3), (0.10, 2), (0.01, 1), (0.0, 0))

# (kind, level) -> word. Level 0 is a trace: something falls, barely.
WORDS = {
    "drizzle": {0: "Sprinkles", 1: "Drizzle", 2: "Rain", 3: "Heavy rain"},
    "rain": {0: "Sprinkles", 1: "Light rain", 2: "Rain", 3: "Heavy rain"},
    "showers": {0: "Sprinkles", 1: "Scattered showers", 2: "Showers", 3: "Downpours"},
    "snow": {0: "Flurries", 1: "Light snow", 2: "Snow", 3: "Heavy snow"},
}
# Older rows without an amount: the code's own intensity.
CODE_LEVEL = {51: 0, 53: 1, 55: 1, 61: 1, 63: 2, 65: 3, 71: 1, 73: 2, 75: 3, 77: 1,
              80: 1, 81: 2, 82: 3, 85: 1, 86: 3}


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def rain_desc(code: Any, precip_in: Any, max_rate: Any, pct: Any) -> Dict[str, Any]:
    """{"label", "severity", "text"} for one game. `text` is what the pages
    show, e.g. "Light rain, 0.05 in (31% chance)" or "40% chance of rain,
    little expected"; None when there's nothing worth saying.

    The weather code picks the kind (drizzle, rain, showers, snow, storms);
    the amount in the wettest hour picks how heavy. Thunderstorms and
    freezing rain keep severity 3 whatever the amount -- lightning delays and
    ice matter even in a light storm. Pure, so it's tested directly."""
    code_n, total, rate, chance = _num(code), _num(precip_in), _num(max_rate), _num(pct)
    kind = KIND.get(int(code_n)) if code_n is not None else None
    if kind is None and rate is not None and rate >= 0.01:
        kind = "rain"                     # an amount with no precip code: call it rain
    if kind is None:
        label, sev = None, 0
    elif kind == "storm":
        label, sev = "Thunderstorms", 3
    elif kind == "freezing":
        label, sev = ("Freezing drizzle" if int(code_n) in (56, 57) else "Freezing rain"), 3
    else:
        if rate is not None:
            level = next(lv for floor, lv in INTENSITY if rate >= floor)
        else:
            level = CODE_LEVEL.get(int(code_n), 1)
        label = WORDS[kind][level]
        sev = level if kind != "snow" else min(3, level + 1)
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
