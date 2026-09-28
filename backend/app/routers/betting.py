"""Cross-sport betting endpoints: the Daily Briefing and the EV Finder's
report card. (The Edge Board, live quotes and the bet log were removed --
see docs/removed-features.md.)"""

import pandas as pd
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_access

router = APIRouter(prefix="/api/betting", tags=["betting"])


# A snapshot older than this is treated as missing (the Actions schedule has
# stopped, or it's the middle of the night) and the briefing is built live.
BRIEFING_MAX_AGE_MIN = 60


@router.get("/briefing")
def briefing(_=Depends(require_access)):
    """Daily Briefing -- see app/data/briefing.py. Served from the snapshot
    GitHub Actions builds every 15 minutes (app/build_briefing.py) so the
    page loads in about a second; built live only when that snapshot is
    missing or stale."""
    from app.data.loader import get_briefing_snapshot
    snap = get_briefing_snapshot()
    made = pd.to_datetime(snap.get("generated_at"), utc=True, errors="coerce") if snap else pd.NaT
    if not pd.isna(made) and pd.Timestamp.now(tz="UTC") - made < pd.Timedelta(minutes=BRIEFING_MAX_AGE_MIN):
        return snap
    from app.data.briefing import get_briefing
    return get_briefing()


@router.get("/report-card")
def report_card(_=Depends(require_access)):
    """How the EV Finder's flagged plays have done against the close."""
    from app.data.report_card import get_report_card
    return get_report_card()
