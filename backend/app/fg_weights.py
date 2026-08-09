"""Fetch and cache FanGraphs' wOBA linear weights.

FanGraphs recomputes the wOBA constants every season and revises the current
year's values as it progresses. Hardcoding them means your wOBA silently drifts
away from theirs. This refreshes them once a day and caches the result.

Resolution order, most to least preferred:

  1. cached values younger than MAX_AGE_HOURS      (no network call)
  2. a fresh fetch from fangraphs.com/guts.aspx
  3. the cache, even if stale                      (warns)
  4. BUILTIN_FALLBACK below                        (warns loudly)

It never hard-fails on a network problem -- a dashboard that keeps running on
yesterday's constants is better than one that crashes.

When a fetch changes a value you were already using, the change is logged with
both numbers, so a wOBA shift is explainable rather than mysterious.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd

log = logging.getLogger("fg_weights")

GUTS_URL = "https://www.fangraphs.com/guts.aspx?type=cn"
MAX_AGE_HOURS = 24
REQUEST_TIMEOUT = 30

#: The six weights wOBA needs, mapped from FanGraphs' column names.
WEIGHT_COLUMNS = ("wBB", "wHBP", "w1B", "w2B", "w3B", "wHR")

#: Last-resort values if there is no cache and no network. Verified against
#: fangraphs.com/guts.aspx -- update occasionally so the floor stays sane.
BUILTIN_FALLBACK: dict[int, dict[str, float]] = {
    2026: {"wBB": 0.698, "wHBP": 0.729, "w1B": 0.889, "w2B": 1.260, "w3B": 1.594, "wHR": 2.046},
    2025: {"wBB": 0.691, "wHBP": 0.722, "w1B": 0.882, "w2B": 1.252, "w3B": 1.584, "wHR": 2.037},
    2024: {"wBB": 0.689, "wHBP": 0.720, "w1B": 0.882, "w2B": 1.254, "w3B": 1.590, "wHR": 2.050},
    2023: {"wBB": 0.696, "wHBP": 0.726, "w1B": 0.883, "w2B": 1.244, "w3B": 1.569, "wHR": 2.004},
    2022: {"wBB": 0.689, "wHBP": 0.720, "w1B": 0.884, "w2B": 1.261, "w3B": 1.601, "wHR": 2.072},
    2021: {"wBB": 0.692, "wHBP": 0.722, "w1B": 0.879, "w2B": 1.242, "w3B": 1.568, "wHR": 2.007},
    2020: {"wBB": 0.699, "wHBP": 0.728, "w1B": 0.883, "w2B": 1.238, "w3B": 1.558, "wHR": 1.979},
}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_guts_html(html: str) -> dict[int, dict[str, float]]:
    """Extract {season: {weight: value}} from the Guts page HTML.

    The page contains several tables, so every candidate is checked for the
    expected columns rather than trusting a fixed index -- FanGraphs changes
    their page layout from time to time.
    """
    tables = pd.read_html(StringIO(html))
    log.debug("found %d tables on the page", len(tables))

    for table in tables:
        columns = {str(c).strip(): c for c in table.columns}
        if "Season" not in columns:
            continue
        if not all(weight in columns for weight in WEIGHT_COLUMNS):
            continue

        frame = table.rename(columns={v: k for k, v in columns.items()})
        seasons = pd.to_numeric(frame["Season"], errors="coerce")
        frame = frame[seasons.notna()].copy()
        frame["Season"] = seasons[seasons.notna()].astype(int)

        weights: dict[int, dict[str, float]] = {}
        for row in frame.itertuples(index=False):
            record = row._asdict()
            season = int(record["Season"])
            try:
                values = {w: float(record[w]) for w in WEIGHT_COLUMNS}
            except (TypeError, ValueError):
                continue
            # Sanity band -- guards against parsing a park-factor table by
            # accident, or a column shift putting nonsense in these fields.
            if not (0.3 < values["wBB"] < 1.2 and 1.2 < values["wHR"] < 3.0):
                log.debug("season %d values out of plausible range, skipped", season)
                continue
            weights[season] = values

        if weights:
            log.info("parsed weights for %d seasons (%d-%d)",
                     len(weights), min(weights), max(weights))
            return weights

    raise ValueError(
        "No table on the Guts page had a Season column plus "
        f"{WEIGHT_COLUMNS}. FanGraphs may have changed their layout."
    )


def fetch_weights(url: str = GUTS_URL, timeout: int = REQUEST_TIMEOUT) -> dict[int, dict[str, float]]:
    import requests

    log.info("fetching wOBA constants from %s", url)
    response = requests.get(
        url,
        headers={
            # FanGraphs rejects requests with no browser-like User-Agent.
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_guts_html(response.text)


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def _read_cache(path: Path) -> tuple[dict[int, dict[str, float]], datetime | None]:
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        weights = {int(k): {kk: float(vv) for kk, vv in v.items()}
                   for k, v in payload.get("weights", {}).items()}
        fetched_at = payload.get("fetched_at")
        stamp = datetime.fromisoformat(fetched_at) if fetched_at else None
        if stamp and stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return weights, stamp
    except Exception as exc:  # noqa: BLE001 - a corrupt cache must not be fatal
        log.warning("could not read weights cache %s (%s); ignoring it", path, exc)
        return {}, None


def _write_cache(path: Path, weights: dict[int, dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": GUTS_URL,
        "weights": {str(k): v for k, v in sorted(weights.items())},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("cached %d seasons of weights to %s", len(weights), path)


def _report_changes(old: dict[int, dict[str, float]],
                    new: dict[int, dict[str, float]],
                    season: int) -> None:
    """Log any change to the season you actually use, with both values.

    This is the point of refreshing: a wOBA shift should be traceable to a
    constant that moved, not left as a mystery.
    """
    before, after = old.get(season), new.get(season)
    if not before or not after:
        return
    changes = [
        (name, before[name], after[name])
        for name in WEIGHT_COLUMNS
        if name in before and name in after and abs(before[name] - after[name]) > 1e-9
    ]
    if not changes:
        log.info("%d weights unchanged since last fetch", season)
        return
    log.warning("FanGraphs revised %d wOBA constants -- your wOBA will shift slightly:", season)
    for name, old_value, new_value in changes:
        log.warning("    %-5s %.4f -> %.4f  (%+.4f)", name, old_value, new_value,
                    new_value - old_value)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def load_weights(
    cache_path: Path,
    season: int,
    *,
    max_age_hours: int = MAX_AGE_HOURS,
    force_refresh: bool = False,
    allow_network: bool = True,
) -> tuple[dict[int, dict[str, float]], str]:
    """Return (weights_by_season, provenance) for use in wOBA.

    Never raises on network trouble -- it degrades to cache, then to the
    built-in table, and says which one it used.
    """
    cached, fetched_at = _read_cache(cache_path)
    now = datetime.now(timezone.utc)
    age = (now - fetched_at) if fetched_at else None

    fresh_enough = (
        cached and age is not None and age < timedelta(hours=max_age_hours)
        and season in cached
    )
    if fresh_enough and not force_refresh:
        hours = age.total_seconds() / 3600
        return cached, f"cache ({hours:.1f}h old, {cache_path.name})"

    if allow_network:
        try:
            fetched = fetch_weights()
            if season in fetched:
                _report_changes(cached, fetched, season)
                _write_cache(cache_path, fetched)
                return fetched, f"fetched from FanGraphs {now.date()}"
            log.warning(
                "fetch succeeded but %d is not in the table yet (latest is %s); "
                "keeping existing values", season, max(fetched) if fetched else "none",
            )
            if fetched:
                _write_cache(cache_path, fetched)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not refresh weights (%s: %s)", type(exc).__name__, exc)

    if cached and season in cached:
        stamp = f"{age.days}d old" if age else "undated"
        log.warning("using STALE cached weights (%s) -- refresh failed", stamp)
        return cached, f"stale cache ({stamp})"

    log.warning(
        "falling back to the built-in weights table. These may be out of date; "
        "check https://www.fangraphs.com/guts.aspx?type=cn"
    )
    return BUILTIN_FALLBACK, "built-in fallback (possibly stale)"


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s",
                        stream=sys.stdout, force=True)
    season = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().year
    here = Path(__file__).resolve().parent
    weights, provenance = load_weights(
        here / "data" / "mlb" / "fg_woba_weights.json", season, force_refresh=True
    )
    print(f"\nprovenance: {provenance}")
    if season in weights:
        print(f"\n{season} wOBA weights:")
        for name in WEIGHT_COLUMNS:
            print(f"  {name:5} {weights[season][name]:.4f}")
    else:
        print(f"\n{season} not present. Seasons available: "
              f"{min(weights)}-{max(weights)}")
