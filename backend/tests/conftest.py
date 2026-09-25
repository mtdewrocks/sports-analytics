import sys
from pathlib import Path

# `app.*` imports resolve from backend/; the plain scripts (build_odds_snapshots,
# get_props) import their siblings from backend/app/ directly.
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "app"))
