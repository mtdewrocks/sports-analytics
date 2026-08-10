"""Download headshots for any starter missing one.

Reads starters.parquet and fetches a photo for every pitcher who does not
already have a file. Existing images are never re-downloaded, so a normal run
does nothing and costs nothing -- only a debut starter triggers a fetch.

Filenames are "{pitcher}.jpg" using the same name the dropdown shows, which is
what the frontend builds its URL from:

    `${IMAGE_BASE}/${encodeURIComponent(selectedPitcher)}.jpg`

Photos come from MLB's image CDN keyed on the player id, so no name matching
is involved -- only the saved filename uses the name.

No arguments:

    python backend/app/get_pitcher_images.py

Reads:  backend/data/mlb/starters.parquet
Writes: backend/data/mlb/pitcher_images/{pitcher}.jpg
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
IMAGE_DIR = DATA_DIR / "pitcher_images"

HEADSHOT = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/"
    "d_people:generic:headshot:67:current.png/w_213,q_auto:best/"
    "v1/people/{pid}/headshot/67/current"
)

TIMEOUT = 30
MIN_BYTES = 1000  # anything smaller is an error page, not a photo


def download(pitcher_id: int, dest: Path) -> bool:
    """Fetch one headshot. Returns True if a file was written."""
    try:
        r = requests.get(HEADSHOT.format(pid=pitcher_id), timeout=TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        print(f"  failed {dest.name}: {e}")
        return False

    # The CDN returns a generic silhouette rather than a 404 for an unknown id.
    # It is still a valid image, so only obviously-empty responses are rejected.
    if len(r.content) < MIN_BYTES:
        print(f"  skipped {dest.name}: response too small ({len(r.content)} bytes)")
        return False

    dest.write_bytes(r.content)
    return True


def main() -> None:
    starters_path = DATA_DIR / "starters.parquet"
    if not starters_path.exists():
        print("no starters.parquet -- run get_starters.py first")
        return

    starters = pd.read_parquet(starters_path)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    missing = []
    for row in starters.itertuples(index=False):
        name = str(row.pitcher).strip()
        if not name or pd.isna(row.pitcher_id):
            continue
        dest = IMAGE_DIR / f"{name}.jpg"
        if not dest.exists():
            missing.append((int(row.pitcher_id), name, dest))

    if not missing:
        print(f"all {len(starters)} starters already have a photo")
        return

    print(f"{len(missing)} starter(s) missing a photo:")
    written = 0
    for pitcher_id, name, dest in missing:
        if download(pitcher_id, dest):
            print(f"  downloaded {name}")
            written += 1

    print(f"wrote {written} of {len(missing)} -> {IMAGE_DIR}")


if __name__ == "__main__":
    main()
