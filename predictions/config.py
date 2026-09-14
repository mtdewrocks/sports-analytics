"""Central config for the hit-predictor pipeline."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # statcast_{year}.parquet (pitch-level)
FEAT_DIR = DATA_DIR / "features"    # daily feature tables
MODEL_DIR = PROJECT_ROOT / "models"
OUT_DIR = PROJECT_ROOT / "output"

# Seasons to download / use. 2015+ = full Statcast era (exit velo, spin,
# reliable pitch classification).
SEASONS = list(range(2015, 2026))

ROLL_DAYS = 30          # short-form rolling window
HARD_HIT_EV = 95.0      # mph threshold for hard-hit
SMOOTH_PA = 60          # pseudo-observations for rate smoothing
MIN_PRIOR_PA = 40       # rows with less batter history than this are dropped from training

# Feature names listed here are excluded from training and prediction.
# Useful for redundancy experiments, e.g.:
#   EXCLUDE_FEATURES = ["lineup_slot", "expected_pa"]
EXCLUDE_FEATURES = []

# Columns kept from the raw statcast pull (keeps files small)
RAW_COLS = [
    "game_pk", "game_date", "game_year", "batter", "pitcher", "player_name",
    "stand", "p_throws", "events", "description", "bb_type", "launch_speed",
    "woba_value", "woba_denom", "at_bat_number", "pitch_number",
    "inning", "inning_topbot", "home_team", "away_team",
    "pitch_type", "release_speed", "pfx_x", "pfx_z", "release_spin_rate",
    "game_type",
]

# usage-smoothing pseudo-pitches for arsenal features
SMOOTH_PITCHES = 200

for d in (RAW_DIR, FEAT_DIR, MODEL_DIR, OUT_DIR):
    d.mkdir(parents=True, exist_ok=True)
