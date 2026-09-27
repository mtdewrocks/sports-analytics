"""Precompute the Daily Briefing so the page never builds it on a request.

Building it pulls a dozen data files and runs every research page's logic
(about 30s on a fast machine, minutes on a small web instance -- long
enough to time out). This runs it in GitHub Actions on a schedule (see
.github/workflows/update_briefing.yml) and publishes the result as
briefing.json; the API serves that file, and only builds live when the
file is missing or stale (routers/betting.py).

    python backend/app/build_briefing.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

OUT = BACKEND / "data" / "nfl" / "briefing.json"


def main() -> None:
    from app.data.briefing import get_briefing
    t = time.time()
    b = get_briefing()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(b, default=str, separators=(",", ":")))
    print(f"{len(b['changes'])} changes, {len(b['games'])} games -> {OUT} in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
