"""Download pitch-level Statcast data season by season via pybaseball.

Run locally (needs internet):  python src/download_data.py [start_year] [end_year]
Saves data/raw/statcast_{year}.parquet. Safe to re-run; skips finished seasons.
"""
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RAW_DIR, RAW_COLS, SEASONS

from pybaseball import statcast, cache

cache.enable()  # caches raw HTTP responses so re-runs are cheap

# month chunks keep each request set small and resumable
CHUNKS = [("03-01", "04-30"), ("05-01", "05-31"), ("06-01", "06-30"),
          ("07-01", "07-31"), ("08-01", "08-31"), ("09-01", "11-15")]


def download_season(year: int, force: bool = False) -> None:
    out = RAW_DIR / f"statcast_{year}.parquet"
    out_excel = RAW_DIR / f"statcast_{year}.xlsx"
    if out.exists() and not force:
        print(f"{year}: already downloaded, skipping (use --force to refresh)")
        return
    parts = []
    for start, end in CHUNKS:
        print(f"{year}: pulling {start} .. {end}")
        df = None
        for attempt in range(1, 6):
            try:
                df = statcast(start_dt=f"{year}-{start}", end_dt=f"{year}-{end}", verbose=False)
                break
            except Exception as e:
                wait = 30 * attempt
                print(f"  attempt {attempt}/5 failed ({type(e).__name__}: {e}); "
                      f"retrying in {wait}s...")
                time.sleep(wait)
        else:
            raise SystemExit(
                f"{year}: chunk {start}..{end} failed 5 times. Re-run this script -- "
                "completed chunks are cached, so it resumes quickly.")
        if df is not None and len(df):
            keep = [c for c in RAW_COLS if c in df.columns]
            parts.append(df[keep])
    if not parts:
        print(f"{year}: no data returned")
        return
    season = pd.concat(parts, ignore_index=True)
    # regular season only (spring training/exhibitions have game_type elsewhere;
    # the search above already defaults to regular season)
    season["game_date"] = pd.to_datetime(season["game_date"])
    season.to_parquet(out, index=False)
    season.to_excel(out_excel, index=False)
    print(f"{year}: saved {len(season):,} pitches -> {out}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    years = SEASONS
    if args:
        start = int(args[0])
        end = int(args[1]) if len(args) >= 2 else start
        years = list(range(start, end + 1))
    for y in years:
        download_season(y, force=force)
