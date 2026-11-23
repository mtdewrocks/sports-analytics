"""Top-picks email, ~30 minutes before tip / kickoff -- NBA and NFL.

TEST MODE (the only mode for now): every email goes to ONE address,
PICK_EMAILS_TEST_TO, and nobody else -- there's no user opt-in yet. Once
the emails look right, rollout is an opt-in column on User plus a toggle on
the account page; the sender below already takes a list of recipients.

How it runs: a background thread in the web app (started in main.py) checks
every CHECK_EVERY_S seconds. Games are grouped by start time (a Sunday 1 PM
NFL window is one email, not eight), and a window is sent once when it's
SEND_FROM_MIN..SEND_UNTIL_MIN minutes from starting. Each send is recorded
in pick_email_log, so a window never goes out twice; after a restart a
window already inside SEND_UNTIL_MIN is skipped rather than sent late.

Picks come from the same functions the projections pages use, at the
current lines -- so the email matches what the site shows at that moment.

Env (all optional; nothing sends unless both are set):
  PICK_EMAILS_ENABLED=true
  PICK_EMAILS_TEST_TO=<address>
Admin preview, ignoring timing and the log (see routers/admin.py):
  POST /api/admin/pick-emails/preview?sport=nba&send=true
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.config import settings
from app.database import Base, SessionLocal
from app.notifications import send_email

logger = logging.getLogger(__name__)

SEND_FROM_MIN = 32        # first check inside this many minutes before start sends it
SEND_UNTIL_MIN = 12       # ...unless it's already this close (restart, outage): skip, don't send late
CHECK_EVERY_S = 300
PER_GAME = 5              # bets per game
HIGHLIGHT = 3             # ...the first this many starred as the top picks
WATCH_PER_GAME = 2        # NFL tracking-only plays per game
NBA_LAST = 10             # "L10 7/10": his last 10 games on the flagged side of this line
NFL_LAST = 5


class PickEmailLog(Base):
    __tablename__ = "pick_email_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sport = Column(String(10), nullable=False)
    window = Column(String(40), nullable=False)        # start time, ISO UTC
    recipient = Column(String(255), nullable=False)
    picks = Column(Integer, default=0)
    sent_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("sport", "window", "recipient", name="uq_pick_email"),)


def _odds(p) -> str:
    return "" if p is None else f"{int(p):+d}"


def _ts(x) -> Optional[pd.Timestamp]:
    if not x:
        return None
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _ct(t: pd.Timestamp) -> str:
    return t.tz_convert("America/Chicago").strftime("%a %-I:%M %p CT")


# ---------------------------------------------------------------- picks
def hit_text(vals, line, side, n: int) -> str:
    """'L10 7/10' -- how many of his last n results landed on the flagged side."""
    vals = [v for v in (vals or []) if v is not None and v == v][-n:]
    if not vals or line is None or side not in ("over", "under"):
        return ""
    hits = sum((v > line) if side == "over" else (v < line) for v in vals)
    return f"L{n} {hits}/{len(vals)}"


def nba_recent() -> Dict[tuple, list]:
    """(player key, market) -> his last NBA_LAST results, oldest first."""
    from app import nba_projection_edges as E
    from app.data.loader import get_nba_all_seasons
    st = get_nba_all_seasons()
    if st is None or st.empty:
        return {}
    st = st[pd.to_numeric(st.get("played", 1), errors="coerce") == 1].copy()
    st["_d"] = pd.to_datetime(st["date"] if "date" in st.columns else st["game_date"])
    st = st.sort_values("_d").groupby("player").tail(NBA_LAST)
    out = {}
    for p, g in st.groupby("player"):
        k = E.match_key(p)
        for m, parts in E.MARKETS.items():
            cols = [c.lower() for c in parts]
            if all(c in g.columns for c in cols):
                out[(k, m)] = g[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1).tolist()
    return out


def nba_why():
    """(player, market, side) -> reasons, from the same models and minutes
    the projections page uses. Fails soft: no reasons, email still goes."""
    try:
        from app import nba_projection_edges as E
        from app import nba_reasons as RS
        from app.data import nba_projections as D
        slate = D.get_projection_slate()
        if slate is None or slate.empty:
            return lambda *a: []
        slate = D._live_status(slate).reset_index(drop=True)
        models, _ = D._cached_boosters()
        mins = slate["default_min"]
        eff = RS.effects(models, slate, mins)
        idx = {E.match_key(p): i for i, p in slate["PLAYER"].items()}
    except Exception:                                   # noqa: BLE001
        logger.exception("pick emails: NBA reasons failed")
        return lambda *a: []

    def get(player, market, side):
        i = idx.get(E.match_key(player))
        if i is None:
            return []
        try:
            return RS.reasons_for(i, slate.loc[i], market, side, eff, slate, float(mins[i]))
        except Exception:                               # noqa: BLE001
            return []
    return get


def nba_games() -> List[dict]:
    """[{start, title, bets: [line, ...], watch: []}] for tonight's slate."""
    from app import nba_projection_edges as E
    from app.data import nba_projections as D
    data = D.get_projections()
    try:
        recent = nba_recent()
    except Exception:                       # noqa: BLE001 -- the email still goes without it
        logger.exception("pick emails: NBA recent games failed")
        recent = {}
    why = nba_why()
    out = []
    for g in data.get("games", []):
        rows = []
        for t in g["teams"]:
            for p in t["players"]:
                for m, e in (p.get("lines") or {}).items():
                    if e.get("side") and e.get("price") is not None and not e.get("suspect"):
                        h = hit_text(recent.get((E.match_key(p["player"]), m)), e["line"], e["side"], NBA_LAST)
                        r = why(p["player"], m, e["side"])
                        vals = recent.get((E.match_key(p["player"]), m)) or []
                        if len(r) < 2 and len(vals) >= 5:
                            avg = sum(vals) / len(vals)
                            if (avg > e["line"]) == (e["side"] == "over") and avg != e["line"]:
                                r = r + [f"averaging {avg:.1f} over his last {len(vals)} vs the {e['line']} line"]
                        rows.append((e["ev"], f"{p['player']} ({t['team']}) {e['side'].upper()} {e['line']} {e['label']} "
                                              f"{_odds(e['price'])} {e.get('book') or ''}" + (f" | {h}" if h else "")
                                              + f" | proj {e['projection']:.1f}, exp. return {round(100 * e['ev'])}%"
                                              + (f"\n      Why: {'; '.join(r)}" if r else "")))
        rows.sort(key=lambda r: -r[0])
        out.append({"start": _ts(g.get("start_utc")), "title": f"{g['away']} @ {g['home']}",
                    "bets": [r[1] for r in rows[:PER_GAME]], "watch": []})
    return out


def nfl_games() -> List[dict]:
    from app import nfl_projection_edges as E
    from app.data import nfl_projections as D
    data = D.get_projections()
    by_game: Dict[str, dict] = {g["game_id"]: {"start": _ts(g["kickoff"]), "title": f"{g['away']} @ {g['home']}",
                                               "bets": [], "watch": []} for g in data.get("games", [])}

    recent = {p["player_id"]: p.get("recent") or {} for p in data.get("players", [])}
    pl = {p["player_id"]: p for p in data.get("players", [])}

    def why(b) -> list:
        from app import nfl_reasons as RS
        try:
            r = RS.reasons_for(pl.get(b.get("player_id")) or {}, b["market"], b["side"])
        except Exception:                                 # noqa: BLE001
            r = []
        vals = [v for v in (recent.get(b.get("player_id"), {}).get(E.MARKETS.get(b["market"])) or [])
                if v is not None][-NFL_LAST:]
        if len(r) < 2 and len(vals) >= 3 and b.get("line") is not None and b["side"] in ("over", "under"):
            avg = sum(vals) / len(vals)
            if (avg > b["line"]) == (b["side"] == "over") and avg != b["line"]:
                r = r + [f"averaging {avg:.1f} over his last {len(vals)} vs the {b['line']} line"]
        return r

    def line(b):
        td = b["market"] == "anytime_td"
        what = f"anytime TD {_odds(b['price'])}" if td else f"{b['side'].upper()} {b['line']} {b['label']} {_odds(b['price'])}"
        proj = f"{round(100 * b['projection'])}% to score" if td else f"proj {b['projection']}"
        h = "" if td else hit_text(recent.get(b.get("player_id"), {}).get(E.MARKETS.get(b["market"])),
                                   b.get("line"), b["side"], NFL_LAST)
        r = why(b)
        return (f"{b['player']} ({b['team']}) {what} {b.get('book') or ''}" + (f" | {h}" if h else "")
                + f" | {proj}, exp. return {round(100 * b['ev'])}%" + (f"\n      Why: {'; '.join(r)}" if r else ""))
    for tier, key, n in (("bet", "bets", PER_GAME), ("watch", "watch", WATCH_PER_GAME)):
        for b in E.best_bets(data.get("players", []), tier, 10_000):
            g = by_game.get(b["game_id"])
            if g is not None and not b.get("suspect") and len(g[key]) < n:
                g[key].append(line(b))
    return list(by_game.values())


SOURCES = {"nba": nba_games, "nfl": nfl_games}
SITE = {"nba": "NBA Projections", "nfl": "NFL Projections"}


# ---------------------------------------------------------------- email
def windows(games: List[dict]) -> Dict[pd.Timestamp, List[dict]]:
    w: Dict[pd.Timestamp, List[dict]] = {}
    for g in games:
        if g["start"] is not None:
            w.setdefault(g["start"], []).append(g)
    return dict(sorted(w.items()))


def compose(sport: str, start: pd.Timestamp, games: List[dict]) -> tuple:
    n = sum(len(g["bets"]) for g in games)
    title = games[0]["title"] if len(games) == 1 else f"{len(games)} games"
    subject = f"{sport.upper()} top picks -- {title}, {_ct(start)}"
    parts = [f"Top picks for the {_ct(start)} {sport.upper()} start, at current lines. "
             f"★ = top {HIGHLIGHT} for that game.", ""]
    for g in games:
        parts.append(g["title"])
        parts += [f"  {'★' if i < HIGHLIGHT else '-'} {b}" for i, b in enumerate(g["bets"])] or ["  (nothing clears the bar)"]
        if g["watch"]:
            parts.append("  Tracking only:")
            parts += [f"    - {w}" for w in g["watch"]]
        parts.append("")
    base = (settings.FRONTEND_URL or "").rstrip("/")
    parts += [f"Full board and live prices: {SITE[sport]}" + (f" at {base}" if base else ""),
              "Prices move -- check yours before betting. Projections, not guarantees; bet only what you can afford to lose.",
              "Gambling problem? Call 1-800-GAMBLER.", "",
              "TEST SEND -- only the test address receives this."]
    return subject, "\n".join(parts), n


def recipients() -> List[str]:
    to = (settings.PICK_EMAILS_TEST_TO or "").strip()
    return [to] if to else []          # rollout: + opted-in users


def run_once(now: Optional[pd.Timestamp] = None, sports=("nba", "nfl")) -> List[str]:
    """Send every window that's due. Returns what was sent (for logs/tests)."""
    now = now or pd.Timestamp.now(tz="UTC")
    to = recipients()
    if not to:
        return []
    sent = []
    db = SessionLocal()
    try:
        for sport in sports:
            try:
                games = SOURCES[sport]()
            except Exception:                                   # noqa: BLE001
                logger.exception("pick emails: %s picks failed", sport)
                continue
            for start, gs in windows(games).items():
                mins = (start - now).total_seconds() / 60
                if not (SEND_UNTIL_MIN < mins <= SEND_FROM_MIN):
                    continue
                key = start.isoformat()
                subject, body, n = compose(sport, start, gs)
                for r in to:
                    if db.query(PickEmailLog).filter_by(sport=sport, window=key, recipient=r).first():
                        continue
                    if n == 0:                                   # nothing to say: log it, send nothing
                        ok = True
                    else:
                        ok = send_email(r, subject, body)
                    if ok:
                        db.add(PickEmailLog(sport=sport, window=key, recipient=r, picks=n))
                        db.commit()
                        sent.append(f"{sport} {key} -> {r} ({n} picks)")
    finally:
        db.close()
    return sent


def preview(sport: str, send: bool = False) -> dict:
    """The next upcoming window's email, regardless of timing; optionally
    send it to the test address (not logged, so the real one still goes)."""
    now = pd.Timestamp.now(tz="UTC")
    ws = {s: g for s, g in windows(SOURCES[sport]()).items() if s > now}
    if not ws:
        return {"sport": sport, "window": None, "subject": None, "body": "No upcoming games on the board."}
    start, gs = next(iter(ws.items()))
    subject, body, n = compose(sport, start, gs)
    out = {"sport": sport, "window": start.isoformat(), "picks": n, "subject": subject, "body": body, "sent_to": []}
    if send:
        out["sent_to"] = [r for r in recipients() if send_email(r, subject, body)]
    return out


def start_background() -> None:
    if not settings.PICK_EMAILS_ENABLED:
        logger.info("pick emails off (PICK_EMAILS_ENABLED not set)")
        return

    def loop():
        time.sleep(60)                     # let startup finish first
        while True:
            try:
                for s in run_once():
                    logger.info("pick email sent: %s", s)
            except Exception:              # noqa: BLE001 -- never kill the loop
                logger.exception("pick emails: run failed")
            time.sleep(CHECK_EVERY_S)
    threading.Thread(target=loop, daemon=True, name="pick-emails").start()
    logger.info("pick emails on (test address only)")
