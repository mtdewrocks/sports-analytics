"""NHL team reference data shared by the pipeline scripts and the web app.

Imported two ways, both of which resolve to this file:
    scripts (python backend/app/get_nhl_data.py):  import nhl_teams
    web app (app.data.nhl):                         from app import nhl_teams

Arena coordinates are for travel distance only (Schedule Spots page), so
city-level precision is plenty. UTC offsets are STANDARD time -- only the
difference between two teams is ever used, and every team shifts together
for daylight saving (Arizona has no team any more).
"""

from __future__ import annotations

import math
import unicodedata
from typing import Dict, Optional, Tuple

# abbrev: (full name, arena lat, arena lon, standard UTC offset)
TEAMS: Dict[str, Tuple[str, float, float, int]] = {
    "ANA": ("Anaheim Ducks", 33.8078, -117.8765, -8),
    "BOS": ("Boston Bruins", 42.3662, -71.0621, -5),
    "BUF": ("Buffalo Sabres", 42.8750, -78.8764, -5),
    "CGY": ("Calgary Flames", 51.0374, -114.0519, -7),
    "CAR": ("Carolina Hurricanes", 35.8033, -78.7219, -5),
    "CHI": ("Chicago Blackhawks", 41.8807, -87.6742, -6),
    "COL": ("Colorado Avalanche", 39.7487, -105.0077, -7),
    "CBJ": ("Columbus Blue Jackets", 39.9693, -83.0061, -5),
    "DAL": ("Dallas Stars", 32.7905, -96.8103, -6),
    "DET": ("Detroit Red Wings", 42.3411, -83.0553, -5),
    "EDM": ("Edmonton Oilers", 53.5469, -113.4979, -7),
    "FLA": ("Florida Panthers", 26.1584, -80.3256, -5),
    "LAK": ("Los Angeles Kings", 34.0430, -118.2673, -8),
    "MIN": ("Minnesota Wild", 44.9448, -93.1010, -6),
    "MTL": ("Montreal Canadiens", 45.4961, -73.5693, -5),
    "NSH": ("Nashville Predators", 36.1592, -86.7785, -6),
    "NJD": ("New Jersey Devils", 40.7334, -74.1711, -5),
    "NYI": ("New York Islanders", 40.7111, -73.7256, -5),
    "NYR": ("New York Rangers", 40.7505, -73.9934, -5),
    "OTT": ("Ottawa Senators", 45.2969, -75.9272, -5),
    "PHI": ("Philadelphia Flyers", 39.9012, -75.1720, -5),
    "PIT": ("Pittsburgh Penguins", 40.4395, -79.9892, -5),
    "SJS": ("San Jose Sharks", 37.3327, -121.9010, -8),
    "SEA": ("Seattle Kraken", 47.6221, -122.3540, -8),
    "STL": ("St. Louis Blues", 38.6268, -90.2027, -6),
    "TBL": ("Tampa Bay Lightning", 27.9427, -82.4518, -5),
    "TOR": ("Toronto Maple Leafs", 43.6435, -79.3791, -5),
    "UTA": ("Utah Mammoth", 40.7683, -111.9011, -7),
    "VAN": ("Vancouver Canucks", 49.2778, -123.1089, -8),
    "VGK": ("Vegas Golden Knights", 36.1029, -115.1784, -8),
    "WSH": ("Washington Capitals", 38.8981, -77.0209, -5),
    "WPG": ("Winnipeg Jets", 49.8928, -97.1436, -6),
}

# Other spellings a source might use for the same team (ESPN's injury feed
# keys teams by display name). Normalised with _norm() before lookup.
_ALIASES = {
    "utah hockey club": "UTA",
    "utah": "UTA",
    "montreal canadiens": "MTL",
    "st louis blues": "STL",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").split())


_BY_NAME = {_norm(v[0]): k for k, v in TEAMS.items()}
_BY_NAME.update({_norm(k): v for k, v in _ALIASES.items()})


def abbrev_for_name(name: Optional[str]) -> Optional[str]:
    """'Florida Panthers' / 'Montréal Canadiens' / 'FLA' -> 'FLA'."""
    if not name:
        return None
    s = str(name).strip()
    if s.upper() in TEAMS:
        return s.upper()
    return _BY_NAME.get(_norm(s))


def full_name(abbrev: str) -> str:
    return TEAMS.get(abbrev, (abbrev,))[0]


def travel_miles(a: Optional[str], b: Optional[str]) -> Optional[float]:
    """Great-circle miles between two teams' arenas; None if either is unknown."""
    if not a or not b or a not in TEAMS or b not in TEAMS:
        return None
    if a == b:
        return 0.0
    _, la1, lo1, _ = TEAMS[a]
    _, la2, lo2, _ = TEAMS[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(3958.8 * 2 * math.asin(math.sqrt(h)), 0)


def tz_shift(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """Hours of clock change going from a's arena to b's (+ = moved east)."""
    if not a or not b or a not in TEAMS or b not in TEAMS:
        return None
    return TEAMS[b][3] - TEAMS[a][3]
