"""Daily Briefing: what changed, and the day's games with their context.

Two sections, both assembled from data the other pages already load:

WHAT CHANGED  (newest first, last CHANGE_HOURS)
  injury   status changes, with who benefits (app/data/injuries.py)
  lineup   MLB lineups well weaker/stronger than usual vs today's starter's
           hand (app/data/mlb_lineups.py)
  move     main prop lines that moved a meaningful amount since
           CHANGE_HOURS ago (odds snapshots vs. the current props file)

THE SLATE  (one card per game, by start time)
  MLB  both starters' recent form and hand, lineup vs usual, weather, a
       worn-down bullpen, run line and total, lineup-posted status
  NFL  notable injuries on either side, the biggest statistical mismatches
       (Mismatches page), weather, spread and total
  Each card carries up to PLAYS_PER_GAME plays for that game (EV Finder and
  Alt-Line), using the Today page's price bands and long-shot rules.

Every block is independent and wrapped: a missing file drops that piece of
context, never the page.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from app.data.loader import ttl_cache

CHANGE_HOURS = 12
SLATE_HOURS = 30          # games starting within this window count as "today"
NFL_FALLBACK_HOURS = 96   # no NFL game today: show the next ones, marked upcoming
PLAYS_PER_GAME = 2
MAX_MOVES = 8
BIG_LINEUP_GAP = 0.025
MISMATCH_MIN_SCORE = 15
NFL_INJURY_STATUSES = {"Out", "Doubtful", "Questionable", "IR"}
NFL_SKILL = {"QB", "RB", "WR", "TE"}
# Main markets watched for line moves, with the smallest move worth
# reporting. A backup's receiving yards going 1.5 -> 0.5 isn't news; a
# starter's rushing yards going 42.5 -> 55.5 is. The line must also have
# started at twice the minimum move, which filters out fringe players.
MOVE_MIN = {
    "nfl": {"pass_yds": 10, "rush_yds": 5, "reception_yds": 5, "rush_reception_yds": 6,
            "receptions": 1, "rush_attempts": 2, "pass_completions": 2, "pass_attempts": 2},
    "mlb": {"pitcher_strikeouts": 1, "pitcher_outs": 2, "pitcher_hits_allowed": 1,
            "total_bases": 1, "hits_runs_rbis": 1},
}


def _key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


def _safe(label: str, fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception as e:
        print(f"Warning: briefing '{label}' failed: {e}")
        return default


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _odds(p: Any) -> str:
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "—"
    return f"+{p}" if p > 0 else str(p)


def _market(m: str) -> str:
    m = str(m or "").replace("_alternate", "")
    for pre in ("batter_", "player_", "pitcher_"):
        if m.startswith(pre):
            m = m[len(pre):]
    return {"rbis": "RBIs", "hits_runs_rbis": "hits + runs + RBIs", "reception_yds": "receiving yards",
            "rush_yds": "rushing yards", "pass_yds": "passing yards", "outs": "outs",
            "strikeouts": "strikeouts", "rush_reception_yds": "rush + rec yards"}.get(m, m.replace("_", " "))


# ── what changed ────────────────────────────────────────────────────────

def _injury_changes() -> List[Dict[str, Any]]:
    from app.data.injuries import get_injury_feed
    out = []
    for sport in ("nfl", "nba", "mlb"):
        for c in get_injury_feed(sport, hours=CHANGE_HOURS):
            notes = []
            for v in ((c.get("impact") or {}).get("volume") or []):
                label = "target share" if v["kind"] == "targets" else "carry share"
                for b in v["beneficiaries"][:2]:
                    still = [ln for ln in b.get("lines", []) if ln.get("moved") == 0]
                    tail = f"; {_market(still[0]['market'])} line still {still[0]['now']:g}" if still else ""
                    notes.append(f"{b['player']} {label} {b['share']:g}% → ~{b['est_share']:g}%{tail}")
            for b in ((c.get("impact") or {}).get("beneficiaries") or [])[:2]:
                notes.append(f"{b['player']} minutes {b['with']} → {b['without']} without him")
            new = c["new_status"]
            out.append({
                "kind": "injury", "sport": sport, "time": c["detected_at"],
                "tag": "OUT" if new == "Out" else ("ACTIVE" if new == "Active" else new.upper()),
                "title": f"{c['player']} ({' '.join(x for x in (c.get('team'), c.get('position')) if x)})"
                         f" {'cleared to play' if new == 'Active' else new.lower()}"
                         + (f", {c['detail']}" if c.get("detail") else ""),
                "detail": " · ".join(notes) or None,
            })
    return out


def _lineup_changes(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for p in report.get("pitchers", []):
        v = p.get("vs_usual")
        if not v or abs(v["diff"]["woba"]) < BIG_LINEUP_GAP:
            continue
        weaker = v["diff"]["woba"] < 0
        missing = [m["player"] for m in v.get("missing", [])[:3]]
        pts = round(v["diff"]["woba"] * 1000)
        out.append({
            "kind": "lineup", "sport": "mlb", "time": None, "tag": "LINEUP",
            "title": f"{p['opposing_team']} {'weaker' if weaker else 'stronger'} than usual vs {p['player']}"
                     + (f": without {', '.join(missing)}" if weaker and missing else ""),
            "detail": f"Lineup wOBA vs {v['hand']}HP {v['today']['woba']:.3f}, ".replace("0.", ".", 1)
                      + f"usual {v['usual']['woba']:.3f}".replace("0.", ".", 1)
                      + f" ({'+' if pts > 0 else ''}{pts}) · "
                      f"K rate {v['today']['k']:.1f}% vs {v['usual']['k']:.1f}%",
        })
    return out


def line_moves(sport: str, props: pd.DataFrame, snaps: pd.DataFrame,
               now: pd.Timestamp, hours: float = CHANGE_HOURS) -> List[Dict[str, Any]]:
    """Main-market lines whose median across books moved meaningfully since
    `hours` ago. Pure given its frames, so it's tested directly."""
    if props.empty or snaps.empty:
        return []
    mins = MOVE_MIN.get(sport, {})
    markets = set(mins)
    cutoff = now - pd.Timedelta(hours=hours)
    start = pd.to_datetime(props["commence_time"], utc=True, errors="coerce")
    cur = props[props["market"].isin(markets) & (start > now)]
    if cur.empty:
        return []
    cur_med = cur.groupby(["event_id", "Player", "market"])["Line"].median()

    s = snaps[snaps["market"].isin(markets)].copy()
    s["_t"] = pd.to_datetime(s["observed_at"], utc=True, errors="coerce", format="mixed")
    s = s[s["_t"] <= cutoff].sort_values("_t")
    if s.empty:
        return []
    before = (s.drop_duplicates(subset=["event_id", "Player", "market", "bookmakers"], keep="last")
              .groupby(["event_id", "Player", "market"])["Line"].median())
    out = []
    for key, now_line in cur_med.items():
        was = before.get(key)
        if was is None or pd.isna(was) or pd.isna(now_line):
            continue
        move = float(now_line) - float(was)
        floor = mins.get(key[2], 1)
        if abs(move) < floor or abs(float(was)) < 2 * floor:
            continue
        out.append({
            "kind": "move", "sport": sport, "time": None, "tag": "LINE MOVE",
            "title": f"{key[1]} {_market(key[2])} {float(was):g} → {float(now_line):g}",
            "detail": None, "_size": abs(move) / max(abs(float(was)), 1.0),
        })
    out.sort(key=lambda x: x["_size"], reverse=True)
    for o in out:
        o.pop("_size", None)
    return out[:MAX_MOVES // 2]


def _moves() -> List[Dict[str, Any]]:
    from app.data.loader import get_odds_snapshots_data, get_props_data
    now = pd.Timestamp.now(tz="UTC")
    out = []
    for sport in ("nfl", "mlb"):
        out += line_moves(sport, get_props_data(sport), get_odds_snapshots_data(sport), now)
    return out


# ── the slate ───────────────────────────────────────────────────────────

def _events(sport: str) -> List[Dict[str, Any]]:
    """Upcoming games from the props file (every game with props posted)."""
    from app.data.loader import get_props_data
    df = get_props_data(sport)
    if df.empty:
        return []
    ev = df[["event_id", "commence_time", "home_team", "away_team"]].drop_duplicates("event_id")
    ev = ev.assign(_t=pd.to_datetime(ev["commence_time"], utc=True, errors="coerce"))
    now = pd.Timestamp.now(tz="UTC")
    for hours, upcoming in ((SLATE_HOURS, False), (NFL_FALLBACK_HOURS, True)):
        sel = ev[(ev["_t"] > now) & (ev["_t"] <= now + pd.Timedelta(hours=hours))]
        if not sel.empty or sport != "nfl":
            break
    return [{"event_id": r["event_id"], "commence_time": str(r["commence_time"]),
             "home_team": r["home_team"], "away_team": r["away_team"], "upcoming": upcoming}
            for r in sel.sort_values("_t").to_dict(orient="records")]


def _plays_by_game(sport: str) -> Dict[str, List[Dict[str, Any]]]:
    """Best plays per event: EV Finder by event_id, Alt-Line by start time
    and team, both limited to Today's price bands and long-shot checks."""
    from app.data.ev import get_ev
    from app.data.today import alt_longshot_ok, ev_longshot_ok, tier
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in get_ev(sport):
        kind = tier(r["price"])
        if r.get("suspicious") or kind is None or (kind == "longshot" and not ev_longshot_ok(r)):
            continue
        side = ("Over" if r["side"] == "over" else "Under") if r["line"] is not None else \
            ("Yes" if r["side"] == "over" else "No")
        line = f" {r['line']:g}" if r["line"] is not None else ""
        by.setdefault(r["event_id"], []).append({
            "label": f"{r['player']} {side}{line} {_market(r['market'])} {_odds(r['price'])}",
            "note": f"EV +{r['ev_pct']:.1f}% at {r['book']}", "rank": r["ev_pct"],
            "longshot": kind == "longshot",
            "bet": {"sport": sport, "event_id": r["event_id"], "player": r["player"], "market": r["market"],
                    "line": r["line"], "side": r["side"], "book": r["book"], "price": r["price"], "tool": "briefing"},
        })
    return by


def _alt_by_start(sport: str) -> Dict[tuple, List[Dict[str, Any]]]:
    from app.data import mlb, nfl
    from app.data.alt_value import get_alt_value
    from app.data.today import alt_longshot_ok, tier
    fn = mlb.get_mlb_hit_rate_sheet if sport == "mlb" else nfl.get_nfl_hit_rate_sheet
    by: Dict[tuple, List[Dict[str, Any]]] = {}
    for lad in get_alt_value(sport, fn):
        cands = [r for r in lad["rungs"] if r.get("flagged")
                 and (tier(r["best_price"]) == "standard"
                      or (tier(r["best_price"]) == "longshot" and alt_longshot_ok(r)))]
        if not cands:
            continue
        best = max(cands, key=lambda r: r["ev_pct"])
        verdict = (lad.get("matchup") or {}).get("verdict")
        by.setdefault((str(lad.get("commence_time")), str(lad.get("team"))), []).append({
            "label": f"{lad['player']} Over {best['line']:g} {_market(lad['market'])} {_odds(best['best_price'])}",
            "note": f"hit {best['season_sample']} this season · last 10 {best['recent_sample']}"
                    + (f" · matchup {verdict}" if verdict else ""),
            "rank": min(best["ev_pct"], 12) / 2,        # below EV plays of the same size
            "longshot": tier(best["best_price"]) == "longshot",
            "bet": {"sport": sport, "event_id": None, "player": lad["player"], "market": lad["market"],
                    "line": best["line"], "side": "over", "book": best["best_book"],
                    "price": best["best_price"], "tool": "briefing"},
        })
    return by


def _mlb_cards(events: List[Dict[str, Any]], report: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.data import mlb
    from app.data.loader import get_mlb_data
    data = get_mlb_data()
    by_team = {}
    for p in report.get("pitchers", []):
        by_team[p["team"]] = p
    throws = {}
    st = data.get("starters", pd.DataFrame())
    if not st.empty:
        throws = dict(zip(st["pitcher"], st["throws"]))
    weather = _safe("mlb weather", lambda: mlb.get_mlb_weather().get("games", []), [])
    pens = _safe("bullpen", mlb.get_bullpen_report, [])
    tired = {b["team"] for b in pens if ((b.get("kpis") or {}).get("3_day") or {}).get("level") == "tired"}
    lines = _safe("mlb lines", mlb._mlb_game_lines_lookup, {})
    matchups = data.get("matchups", pd.DataFrame())
    posted = set(matchups["team"]) if not matchups.empty else set()
    ev_plays = _safe("mlb plays", lambda: _plays_by_game("mlb"), {})
    alt_plays = _safe("mlb alt", lambda: _alt_by_start("mlb"), {})

    cards = []
    for e in events:
        home, away = e["home_team"], e["away_team"]
        sps = []
        for team in (away, home):
            p = by_team.get(team)
            if not p:
                sps.append({"team": team, "pitcher": None})
                continue
            sps.append({"team": team, "pitcher": p["player"], "throws": throws.get(p["player"]),
                        "games": p.get("games"), "avg_so": p.get("avg_so"), "avg_outs": p.get("avg_outs"),
                        "avg_er": p.get("avg_er")})
        flags = []
        for team in (away, home):
            p = by_team.get(team)
            v = (p or {}).get("vs_usual")
            if v and abs(v["diff"]["woba"]) >= 0.015:
                pts = round(v["diff"]["woba"] * 1000)
                miss = ", ".join(m["player"] for m in v.get("missing", [])[:2])
                flags.append({"kind": "lineup", "tone": "good" if pts < 0 else "bad",
                              "text": f"{p['opposing_team']} {'weaker' if pts < 0 else 'stronger'} than usual vs "
                                      f"{v['hand']}HP ({'+' if pts > 0 else ''}{pts} wOBA)"
                                      + (f", {miss} out" if pts < 0 and miss else "")})
        wx = next((w for w in weather if w.get("home_team") == home), None)
        if wx:
            if wx.get("roof") not in (None, "outdoor", "open"):
                flags.append({"kind": "weather", "tone": "neutral", "text": "Roof closed"})
            else:
                eff = (wx.get("wind_effect") or {}).get("label")
                flags.append({"kind": "weather",
                              "tone": "warn" if (wx.get("wind_mph") or 0) >= 10 or (wx.get("precip_pct") or 0) >= 40 else "neutral",
                              "text": f"{wx.get('temp_f')}°F, wind {wx.get('wind_mph')} mph {wx.get('wind_dir') or ''}".strip()
                                      + (f": {eff}" if eff and (wx.get('wind_mph') or 0) >= 10 else "")})
        for team in (away, home):
            if team in tired:
                flags.append({"kind": "bullpen", "tone": "bad",
                              "text": f"{team} bullpen heavily used the last 3 days"})
        gl = lines.get((home, away))
        line_txt = None
        if gl is not None:
            sp_, tot = _num(gl.get("spread_line")), _num(gl.get("total_line"))
            parts = []
            if sp_ is not None:
                fav = home if sp_ > 0 else away
                parts.append(f"{fav.split()[-1]} -{abs(sp_):g}")
            if tot is not None:
                parts.append(f"O/U {tot:g}")
            line_txt = " · ".join(parts) or None
        plays = list(ev_plays.get(e["event_id"], []))
        for team in (home, away):
            plays += alt_plays.get((e["commence_time"], team), [])
        plays.sort(key=lambda p: p["rank"], reverse=True)
        cards.append({
            "sport": "mlb", **e, "line": line_txt, "starters": sps, "flags": flags,
            "lineups_posted": home in posted and away in posted,
            "lineups_missing": [t for t in (away, home) if t not in posted],
            "plays": [{k: v for k, v in p.items() if k != "rank"} for p in plays[:PLAYS_PER_GAME]],
            "links": [{"label": "Pitcher report", "to": "/mlb/pitcher-daily-report"},
                      {"label": "Team matchup", "to": "/mlb/team-matchup"},
                      {"label": "Props", "to": "/mlb/props"}],
        })
    return cards


def _nfl_cards(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.data import nfl
    from app.data.loader import get_injuries_data, get_nfl_game_lines
    abbr = nfl.NFL_TEAM_ABBR
    inj = _safe("nfl injuries", lambda: get_injuries_data("nfl"), pd.DataFrame())
    weather = _safe("nfl weather", lambda: nfl.get_nfl_weather().get("games", []), [])
    gl = _safe("nfl lines", get_nfl_game_lines, pd.DataFrame())
    mism: List[Dict[str, Any]] = []
    for cat in ("passing", "rushing"):
        res = _safe(f"mismatch {cat}", lambda c=cat: nfl.get_weekly_mismatches(c), {})
        for g in res.get("games", []) if isinstance(res, dict) else []:
            if (g.get("score") or 0) >= MISMATCH_MIN_SCORE:
                mism.append({**g, "cat": cat, "off_label": res.get("offense_label"), "def_label": res.get("defense_label")})
    ev_plays = _safe("nfl plays", lambda: _plays_by_game("nfl"), {})
    alt_plays = _safe("nfl alt", lambda: _alt_by_start("nfl"), {})

    def ordinal(n: int) -> str:
        return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

    cards = []
    for e in events:
        home, away = e["home_team"], e["away_team"]
        ha, aa = abbr.get(home), abbr.get(away)
        flags = []
        if not inj.empty:
            sub = inj[inj["team"].isin([home, away]) & inj["status"].isin(NFL_INJURY_STATUSES)
                      & inj["position"].isin(NFL_SKILL)]
            order = {"Out": 0, "IR": 0, "Doubtful": 1, "Questionable": 2}
            for r in sorted(sub.to_dict(orient="records"), key=lambda r: order.get(r["status"], 3))[:4]:
                flags.append({"kind": "injury", "tone": "bad",
                              "text": f"{r['player']} ({abbr.get(r['team'], r['team'])} {r['position']}) {r['status']}"
                                      + (f", {r['detail']}" if isinstance(r.get('detail'), str) and r['detail'] else "")})
        for g in mism:
            if {g.get("offense_team"), g.get("defense_team")} == {ha, aa}:
                flags.append({"kind": "mismatch", "tone": "good",
                              "text": f"{g['offense_team']} {g['off_label']} ({ordinal(int(g['offense_rank']))}) vs "
                                      f"{g['defense_team']} {g['def_label']} ({ordinal(int(g['defense_rank']))})"})
        wx = next((w for w in weather if w.get("home_team") == ha), None)
        if wx and wx.get("roof") in (None, "outdoor", "open"):
            txt = f"{wx.get('temp_f')}°F, wind {wx.get('wind_mph')} mph {wx.get('wind_dir') or ''}".strip()
            if (wx.get("precip_pct") or 0) >= 30:
                txt += f", {wx['precip_pct']}% rain"
            flags.append({"kind": "weather", "tone": "warn" if (wx.get("wind_mph") or 0) >= 15 else "neutral",
                          "text": txt})
        line_txt = None
        if not gl.empty:
            row = gl[(gl["home_team"] == home) & (gl["away_team"] == away)]
            if not row.empty:
                r = row.iloc[-1]
                sp_, tot = _num(r.get("spread_line")), _num(r.get("total_line"))
                parts = []
                if sp_ is not None and sp_ != 0:
                    fav = ha if sp_ > 0 else aa
                    parts.append(f"{fav} -{abs(sp_):g}")
                if tot is not None:
                    parts.append(f"O/U {tot:g}")
                line_txt = " · ".join(parts) or None
        plays = list(ev_plays.get(e["event_id"], []))
        for team in (home, away):
            plays += alt_plays.get((e["commence_time"], team), [])
        plays.sort(key=lambda p: p["rank"], reverse=True)
        cards.append({
            "sport": "nfl", **e, "line": line_txt, "starters": [], "flags": flags, "lineups_posted": None,
            "plays": [{k: v for k, v in p.items() if k != "rank"} for p in plays[:PLAYS_PER_GAME]],
            "links": [{"label": "Team matchup", "to": "/nfl/matchup"},
                      {"label": "Usage", "to": "/nfl/team-usage"},
                      {"label": "Props", "to": "/nfl/props"}],
        })
    return cards


@ttl_cache(300)
def get_briefing() -> Dict[str, Any]:
    from app.data import mlb
    report = _safe("pitcher report", mlb.get_pitcher_daily_report, {"pitchers": []})
    changes = (_safe("injuries", _injury_changes, []) + _safe("lineups", lambda: _lineup_changes(report), [])
               + _safe("moves", _moves, []))
    changes.sort(key=lambda c: c.get("time") or "", reverse=True)
    games = (_safe("mlb slate", lambda: _mlb_cards(_events("mlb"), report), [])
             + _safe("nfl slate", lambda: _nfl_cards(_events("nfl")), []))
    games.sort(key=lambda g: g["commence_time"])
    return {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "changes": changes, "games": games}
