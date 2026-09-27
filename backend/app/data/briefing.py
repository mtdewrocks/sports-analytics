"""Daily Briefing: what changed, and the day's games with their context.

Two sections, both assembled from data the other pages already load:

WHAT CHANGED  (grouped by kind on the page, newest first within each)
  injury   status changes in the last CHANGE_HOURS, with who benefits
           (app/data/injuries.py) -- only players with real prop lines
           posted (not just TD-scorer odds), volume we can see moving, or
           (NFL) a regular share of snaps at his position (SNAP_FLOOR).
           Deep backups are left out.
  weather  every slate game outdoors with wind, gusts, rain or cold worth
           knowing -- the worst of the game window, not just the start --
           with a plain-English line on what it does (weather_note) and the
           rain in words: drizzle, light rain, downpours (weather_words.py)
  usage    NFL players whose target or carry share over the last couple of
           games is well above or below their earlier games (usage_trends)
  lineup   MLB lineups well weaker/stronger than usual vs today's starter's
           hand (app/data/mlb_lineups.py)
  move     main prop lines that moved a meaningful amount since
           CHANGE_HOURS ago (odds snapshots vs. the current props file)

THE SLATE  (one card per game, by start time)
  MLB  both starters' recent form and hand, lineup vs usual, weather, a
       worn-down bullpen, run line and total, lineup-posted status
  NFL  skill-position injuries; injured starters on the O-line, in the
       secondary and in the front seven, grouped per unit with the prop
       each one touches (trench_groups); the biggest statistical
       mismatches (Mismatches page), weather, usage trends, spread and total
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
# Non-skill units, grouped on the game card. A player counts as a starter
# when he's played STARTER_SNAP_PCT of his side's snaps in the games he's
# played among his team's last STARTER_GAMES.
UNITS = {
    "oline": ({"G", "OG", "OT", "T", "C", "OL"}, "O-line"),
    "secondary": ({"CB", "S", "SS", "FS", "DB"}, "Secondary"),
    "front": ({"DE", "DT", "NT", "DL", "LB", "ILB", "OLB", "MLB", "EDGE"}, "Front seven"),
}
STARTER_SNAP_PCT = 0.60
# A "regular" at a skill position plays less than every snap: backs and
# receivers rotate. QBs don't -- a backup QB's snaps are near zero.
SNAP_FLOOR = {"QB": 0.60, "RB": 0.35, "WR": 0.40, "TE": 0.40, "FB": 0.40}
STARTER_GAMES = 4
OUT_STATUSES = {"Out", "Doubtful", "IR"}
MAX_USAGE = 8
GUST_FACTOR = 1.6         # gusts / this ~ an equivalent steady wind (see weather_note)
GUST_MAX_BUMP = 5         # ...but gusts lift the steady wind by at most this many mph
USAGE_MIN_DIFF = 0.10     # 10 points of team share
USAGE_MIN_DIFF_ONE = 0.12 # stricter when the recent window is a single game (weeks 2-3)
USAGE_MIN_SHARE = 0.15    # the higher of the two windows must be a real role
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


def _nick(team: str) -> str:
    """"Kansas City Royals" -> "Royals"; the two Sox and the Blue Jays keep both words."""
    w = str(team or "").split()
    return " ".join(w[-2:]) if len(w) > 1 and w[-1] in ("Sox", "Jays") else (w[-1] if w else "")


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

# Touchdown scorer markets are posted for nearly every rostered skill player,
# third-string included, so having one says nothing about a role.
ROLE_BLIND_MARKETS = {"anytime_td", "1st_td", "last_td"}


def _props_players(sport: str) -> set:
    """Players with at least one prop that books only post for real roles:
    yards, receptions, strikeouts... -- not touchdown-scorer markets."""
    from app.data.loader import get_props_data
    df = get_props_data(sport)
    if df.empty:
        return set()
    df = df[~df["market"].isin(ROLE_BLIND_MARKETS)]
    return {_key(p) for p in df["Player"].dropna().unique()}


def _injury_changes() -> List[Dict[str, Any]]:
    from app.data.injuries import get_injury_feed
    out = []
    starters = _safe("nfl starters", lambda: nfl_starters(), {})
    from app.data import nfl
    abbr = nfl.NFL_TEAM_ABBR
    for sport in ("nfl", "nba", "mlb"):
        with_props = _safe(f"{sport} props players", lambda sp=sport: _props_players(sp), set())
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
            # Only changes worth a bettor's attention: he has real prop lines
            # posted (not just TD-scorer odds), his volume is going
            # somewhere, or (NFL) he plays a regular share of snaps at his
            # position. Deep backups -- a third-string QB ruled out as a
            # coach's decision -- are left out.
            key = (bool(c.get("impact")) or _key(c["player"]) in with_props
                   or (sport == "nfl" and (abbr.get(c.get("team"), c.get("team")), _key(c["player"])) in starters))
            if not key:
                continue
            out.append({
                "kind": "injury", "sport": sport, "time": c["detected_at"],
                "tag": "OUT" if new == "Out" else ("ACTIVE" if new == "Active" else new.upper()),
                "title": f"{c['player']} ({' '.join(x for x in (c.get('team'), c.get('position')) if x)})"
                         f" {'cleared to play' if new == 'Active' else (new if new[:2] in ('IR', 'IL', 'PU') else new.lower())}"
                         + (f", {c['detail']}" if c.get("detail") else ""),
                "detail": " · ".join(notes) or None,
                "was": c.get("old_status"),
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


def weather_note(sport: str, wind: Optional[float], precip: Optional[float],
                 temp: Optional[float], wind_effect: Optional[str] = None,
                 gust: Optional[float] = None, rain: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """What the weather does, in one line, or None when it's unremarkable.

    Wind and gusts are the worst hour of the game, not just the start
    (get_weather_forecast.py). `rain` is weather_words.rain_desc() -- a word
    and a severity; without it (an older forecast file) the chance of rain
    alone is used.

    NFL numbers come from nflverse play-by-play, 2015-2025, outdoor games,
    each team-game compared with that team's own season average:
      wind 10-14 mph  40-50 yd field goals ~6-8 pts less likely; passing
                      barely moves; games went under the closing total 59%
                      of the time (425 games; 59-60% in both 2015-19 and
                      2020-25)
      wind 15+        completion rate -1.4 (15-19) to -3.0 pts (20+), about
                      15 fewer passing yards per team (-0.4 yds/dropback x
                      ~38 dropbacks); coaches try long field goals less
                      (4th down at the opp 25-37: FG 74% calm, 56% at 20+);
                      unders 57% at 15-19, even at 20+ (the market already
                      drops those totals)
      rain            run rate +2 pts in neutral situations, completion -2.4
                      pts, ~17 fewer passing yards per team; unders 67% of
                      133 games, 4.3 pts below the total on average
      snow            run rate +6 pts (small sample: 23 games)
    History has sustained wind only, no gusts. Gusts are folded in as
    gust / 1.6 (a typical gust factor) once gusts reach 20 mph, capped at
    5 mph above the steady wind -- so 12 mph with gusts of 25+ counts as a
    strong-wind (15+) day, but never as a 20+ day.
    MLB: 10+ mph (or gusts 20+) matters in whichever direction it blows
    (wind_effect is mlb.py's sentence for that); steady rain matters for
    pitcher props, since a delay can end a starter's day early. Pure, so
    it's tested directly."""
    wind, gust, precip = wind or 0, gust or 0, precip or 0
    parts: List[tuple] = []          # (tone, tag, sentence)
    label = (rain or {}).get("label")
    sev = (rain or {}).get("severity", 0)
    storm = bool(label and label.startswith("Thunder"))
    # Gusts only move the needle once they're real gusts (20+ mph); a 6 mph
    # day with gusts to 18 is still a calm day.
    # They also add at most GUST_MAX_BUMP mph to the steady wind: a 12 mph day
    # with gusts to 32 plays like a strong-wind day, not a 20 mph gale.
    eff = max(wind, min(gust / GUST_FACTOR, wind + GUST_MAX_BUMP)) if gust >= 20 else wind
    if sport == "nfl":
        gusts = f" (gusts to {gust:.0f})" if gust >= wind + 5 else ""
        if eff >= 20:
            parts.append(("warn", "WIND", f"Very windy{gusts}: completion rate ~3 pts lower and about 15 fewer "
                                          "passing yards per team; long field goals often aren't tried."))
        elif eff >= 15:
            parts.append(("warn", "WIND", f"Strong wind{gusts}: completion rate ~1.5 pts lower and about 15 fewer "
                                          "passing yards per team; 40+ yard kicks less likely. Unders hit 57% "
                                          "in these games since 2015."))
        elif eff >= 10:
            parts.append(("warn", "WIND", f"Moderate wind{gusts}: 40-50 yard field goals ~6-8 pts less likely; "
                                          "passing barely affected. Unders hit 59% in these games since 2015."))
        if rain is not None:
            if label and "now" in label:
                parts.append(("warn", "SNOW", f"{label}: teams have run ~6 pts more often in snow; "
                                              "passing yards down."))
            elif sev >= 2:
                parts.append(("warn", "STORM" if storm else "RAIN",
                              f"{label}: teams run ~2 pts more often and throw for about 17 fewer yards; "
                              "rain games went under 67% of the time since 2015."
                              + (" Lightning can pause play." if storm else "")))
            elif sev == 1:
                parts.append(("neutral", "RAIN", f"{label}: a small drag at most; it's steady rain that has "
                                                 "pushed totals under."))
        elif precip >= 40:
            parts.append(("neutral", "RAIN", "Rain possible: if it rains, teams run a bit more and totals "
                                             "have tended to go under."))
        if temp is not None and temp <= 32:
            parts.append(("neutral", "COLD", "Freezing: a small drag on passing and kicking."))
    else:
        if eff >= 10:
            parts.append(("warn", "WIND", (wind_effect or "Wind strong enough to move fly balls.").replace(" -- ", ": ")))
        if rain is not None:
            if storm:
                parts.append(("warn", "STORM", "Thunderstorms: a delay is likely and could end the starters' day early."))
            elif sev >= 2:
                parts.append(("warn", "RAIN", f"{label}: a delay could cut the starters' outings short."))
            elif sev == 1:
                parts.append(("neutral", "RAIN", f"{label}: usually played through."))
        elif precip >= 40:
            parts.append(("warn", "RAIN", "Rain risk: a delay could cut the starters' outings short."))
        if temp is not None and temp <= 50:
            parts.append(("neutral", "COLD", "Cold: the ball carries less; a small lean to unders."))
        elif temp is not None and temp >= 88:
            parts.append(("neutral", "HEAT", "Hot: the ball carries farther; a small lean to overs."))
    if not parts:
        return None
    warn = [p for p in parts if p[0] == "warn"]
    return {"tone": "warn" if warn else "neutral", "tag": (warn or parts)[0][1],
            "why": " ".join(p[2] for p in parts)}


def weather_text(wx: Dict[str, Any]) -> str:
    """"65°F, wind 12 mph NE (gusts 29), Light rain, 0.05 in (31% chance)"."""
    wind, gust = wx.get("wind_mph"), wx.get("wind_gust_mph")
    txt = f"{wx.get('temp_f')}°F, wind {wind} mph {wx.get('wind_dir') or ''}".strip()
    if gust is not None and wind is not None and gust >= wind + 5:
        txt += f" (gusts {gust})"
    if wx.get("rain"):
        txt += f", {wx['rain'][0].lower() + wx['rain'][1:]}"
    elif "rain" not in wx and (wx.get("precip_pct") or 0) >= 30:
        txt += f", {wx['precip_pct']}% rain"
    return txt


def _rain(wx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return {"label": wx.get("rain_label"), "severity": wx.get("rain_severity") or 0} if "rain" in wx else None


def _weeks(ws: List[Any]) -> str:
    ws = [int(w) for w in ws]
    if len(ws) == 1:
        return f"Week {ws[0]}"
    if ws == list(range(ws[0], ws[-1] + 1)):
        return f"Weeks {ws[0]}–{ws[-1]}"
    return "Weeks " + ", ".join(str(w) for w in ws)


def usage_trends(usage: pd.DataFrame, teams: set, names: Dict[str, str],
                 positions: Dict[str, str]) -> List[Dict[str, Any]]:
    """NFL players whose share of team targets (or carries, for backs) over
    the team's last few games differs by USAGE_MIN_DIFF or more from their
    earlier games this season.

    Recent window: the team's last 3 games once it has played 6, last 2
    once it has played 4, and early in the season just the last one (with a
    stricter USAGE_MIN_DIFF_ONE). Every recent game must sit on the same
    side of the earlier average, so one big game inside a longer window
    doesn't count as a trend. Shares are recomputed from
    counts over each window. Pure given its frames, so it's tested directly."""
    if usage.empty:
        return []
    u = usage[usage["season"] == usage["season"].max()]
    u = u[u["posteam"].isin(teams)] if teams else u
    out = []
    for team, grp in u.groupby("posteam"):
        weeks = sorted(grp["week"].dropna().unique())
        n = 3 if len(weeks) >= 6 else (2 if len(weeks) >= 4 else 1)
        if len(weeks) < n + 1:
            continue
        min_diff = USAGE_MIN_DIFF if n > 1 else USAGE_MIN_DIFF_ONE
        recent_w, base_w = weeks[-n:], weeks[:-n]
        for stat, share_positions, label in (("targets", {"WR", "TE", "RB"}, "target share"),
                                             ("carries", {"RB"}, "carry share")):
            wk_tot = grp.groupby("week")[stat].sum()
            for pid, pg in grp.groupby("player_id"):
                if positions.get(pid) not in share_positions:
                    continue
                by_w = pg.groupby("week")[stat].sum()
                played_base = [w for w in base_w if w in by_w.index]
                if not played_base or any(w not in by_w.index for w in recent_w):
                    continue      # missed a recent game: that's injury news, not usage
                base_tot = wk_tot.loc[played_base].sum()
                rec_tot = wk_tot.loc[recent_w].sum()
                if base_tot <= 0 or rec_tot <= 0:
                    continue
                base = by_w.loc[played_base].sum() / base_tot
                rec = by_w.loc[recent_w].sum() / rec_tot
                diff = rec - base
                if abs(diff) < min_diff or max(base, rec) < USAGE_MIN_SHARE:
                    continue
                per_game = [by_w[w] / wk_tot[w] for w in recent_w if wk_tot[w] > 0]
                if not all((g > base) if diff > 0 else (g < base) for g in per_game):
                    continue
                name = names.get(pid) or pg["player"].iloc[-1]
                out.append({
                    "kind": "usage", "sport": "nfl", "time": None, "tag": "UP" if diff > 0 else "DOWN",
                    "title": f"{name} ({team} {positions.get(pid)}) {label} "
                             f"{base * 100:.0f}% → {rec * 100:.0f}%",
                    "detail": f"{_weeks(recent_w)} vs {_weeks(played_base).lower()}",
                    "player": name, "stat": stat, "team": team, "_size": abs(diff),
                    "flag": f"{name} {label} {base * 100:.0f}% → {rec * 100:.0f}% ({_weeks(recent_w)})",
                })
    out.sort(key=lambda x: x["_size"], reverse=True)
    for o in out:
        o.pop("_size", None)
    return out[:MAX_USAGE]


def _usage(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """usage_trends for teams on the NFL slate, with each player's current
    main line so it's clear whether the market has caught up."""
    from app.data import nfl
    from app.data.loader import get_nfl_player_week_usage, get_nfl_rosters, get_props_data
    abbr = nfl.NFL_TEAM_ABBR
    teams = {abbr.get(t) for e in events for t in (e["home_team"], e["away_team"])} - {None}
    if not teams:
        return []
    ro = get_nfl_rosters()
    names = dict(zip(ro["player_id"], ro["full_name"])) if not ro.empty else {}
    pos = dict(zip(ro["player_id"], ro["position"])) if not ro.empty else {}
    items = usage_trends(get_nfl_player_week_usage(), teams, names, pos)
    props = get_props_data("nfl")
    if not props.empty:
        props = props.assign(_k=props["Player"].map(_key))
    for it in items:
        mk = "reception_yds" if it["stat"] == "targets" else "rush_yds"
        if not props.empty:
            rows = props[(props["_k"] == _key(it["player"])) & (props["market"] == mk)]
            if not rows.empty:
                it["detail"] += f" · {_market(mk)} line {rows['Line'].median():g}"
        it.pop("player"), it.pop("stat")
    return items


def _attach_usage(games: List[Dict[str, Any]], usage: List[Dict[str, Any]]) -> None:
    """Usage trends onto their NFL game cards (at most 2 per game), then drop
    the card-only fields from the alert items."""
    from app.data import nfl
    abbr = nfl.NFL_TEAM_ABBR
    for g in games:
        if g["sport"] != "nfl":
            continue
        teams = {abbr.get(g["home_team"]), abbr.get(g["away_team"])}
        mine = [u for u in usage if u.get("team") in teams][:2]
        g["flags"] += [{"kind": "usage", "tone": "good" if u["tag"] == "UP" else "bad", "text": u["flag"]}
                       for u in mine]
    for u in usage:
        u.pop("team", None), u.pop("flag", None)


# ── NFL units: linemen and defenders ────────────────────────────────────

def starters_from_snaps(snaps: pd.DataFrame) -> Dict[tuple, Dict[str, Any]]:
    """{(team, name key): {"pct", "position"}} for every player averaging
    STARTER_SNAP_PCT of his side's snaps (SNAP_FLOOR at skill positions;
    offense for linemen and skill players, defense for defenders) in the games he played among his team's last STARTER_GAMES
    this season. Averaging over games he played, not all games, keeps a
    starter who got hurt last week a starter. Pure, so it's tested directly."""
    if snaps.empty:
        return {}
    d = snaps[snaps["season"] == snaps["season"].max()]
    unit_of = {pos: u for u, (poss, _) in UNITS.items() for pos in poss}
    unit_of.update({pos: "skill" for pos in SNAP_FLOOR})
    d = d[d["position"].isin(unit_of)]
    out = {}
    for team, grp in d.groupby("team"):
        weeks = sorted(grp["week"].dropna().unique())[-STARTER_GAMES:]
        g = grp[grp["week"].isin(weeks)]
        for name, pg in g.groupby("player"):
            pos = pg["position"].iloc[-1]
            col = "offense_pct" if unit_of[pos] in ("oline", "skill") else "defense_pct"
            pct = float(pg[col].mean())
            if pct >= SNAP_FLOOR.get(pos, STARTER_SNAP_PCT):
                out[(team, _key(name))] = {"pct": pct, "position": pos}
    return out


@ttl_cache(300)
def nfl_starters() -> Dict[tuple, Dict[str, Any]]:
    from app.data.loader import get_nfl_snap_counts
    return starters_from_snaps(get_nfl_snap_counts())


def trench_groups(inj: pd.DataFrame, team: str, starters: Dict[tuple, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Injured starters on one team, per unit: [{"unit", "label", "out",
    "questionable"}], where each list holds "Name (POS)". Only units with a
    starter out/doubtful/IR, or two questionable, are returned. `team` is the
    abbreviation; `inj` has the injury file's columns plus `abbr`. Pure."""
    rows = inj[inj["abbr"] == team] if not inj.empty else inj
    out = []
    for unit, (poss, label) in UNITS.items():
        hurt, q = [], []
        for r in rows[rows["position"].isin(poss)].to_dict(orient="records"):
            if (team, _key(r["player"])) not in starters:
                continue
            tag = f"{r['player']} ({r['position']})"
            if r["status"] in OUT_STATUSES:
                hurt.append(tag)
            elif r["status"] == "Questionable":
                q.append(tag)
        if hurt or len(q) >= 2:
            out.append({"unit": unit, "label": label, "out": hurt, "questionable": q})
    return out


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


@ttl_cache(300)
def _nfl_roles() -> Dict[str, Any]:
    """Per team: the QB (most offense snaps lately) and the season leaders in
    target share at WR and TE and carry share at RB; plus each defense's
    sacks and rank. What the unit notes point at."""
    from app.data.loader import get_nfl_player_week_usage, get_nfl_rosters, get_nfl_snap_counts, get_nfl_team_stats
    roles: Dict[str, Any] = {"qb": {}, "wr": {}, "te": {}, "rb": {}, "sacks": {}}
    sn = get_nfl_snap_counts()
    if not sn.empty:
        sn = sn[(sn["season"] == sn["season"].max()) & (sn["position"] == "QB")]
        last = sn.sort_values("week").groupby("team").tail(2)
        for team, g in last.groupby("team"):
            roles["qb"][team] = g.groupby("player")["offense_pct"].mean().idxmax()
    u = get_nfl_player_week_usage()
    ro = get_nfl_rosters()
    if not u.empty and not ro.empty:
        u = u[u["season"] == u["season"].max()]
        names = dict(zip(ro["player_id"], ro["full_name"]))
        pos = dict(zip(ro["player_id"], ro["position"]))
        tot = u.groupby("posteam")[["targets", "carries"]].sum()
        per = u.groupby(["posteam", "player_id"])[["targets", "carries"]].sum().reset_index()
        per = per.join(tot, on="posteam", rsuffix="_team")
        for key, stat, want in (("wr", "targets", "WR"), ("te", "targets", "TE"), ("rb", "carries", "RB")):
            sub = per[per["player_id"].map(pos) == want]
            sub = sub.assign(share=sub[stat] / sub[f"{stat}_team"].where(sub[f"{stat}_team"] > 0))
            for team, g in sub.dropna(subset=["share"]).groupby("posteam"):
                r = g.loc[g["share"].idxmax()]
                roles[key][team] = (names.get(r["player_id"]) or r["player_id"], float(r["share"]))
    ts = get_nfl_team_stats()
    if not ts.empty and "Defensive Sacks" in ts.columns:
        for r in ts.to_dict(orient="records"):
            rk = _num(r.get("Rank - Defensive Sacks"))
            roles["sacks"][r["team"]] = (int(r["Defensive Sacks"]), int(rk) if rk else None)
    return roles


def _if_they_sit(n_out: int, note: Optional[str]) -> Optional[str]:
    """Only questionable players in the unit: the note is conditional."""
    if not note or n_out:
        return note
    return "If they sit: " + note[0].lower() + note[1:]


def _unit_note(unit: str, team: str, opp: str, roles: Dict[str, Any], line: Callable[[str, str], Optional[float]],
               safeties_only: bool = False) -> Optional[str]:
    """The prop an injured unit touches, in one sentence."""
    def with_line(name: str, market: str) -> str:
        ln = line(name, market)
        return f"{_market(market)} line {ln:g}" if ln is not None else "no line posted yet"
    if unit == "oline":
        qb = roles["qb"].get(team)
        if not qb:
            return None
        sk = roles["sacks"].get(opp)
        rush = ""
        if sk and sk[1]:
            rush = f"; {opp} has {sk[0]} sacks ({_ordinal(sk[1])})" + (
                ", a top-10 pass rush" if sk[1] <= 10 else ", a weak pass rush, so less risk" if sk[1] >= 23 else "")
        return f"Watch {qb}: {with_line(qb, 'pass_yds')}{rush}."
    if unit == "secondary":
        te = roles["te"].get(opp)
        pick = te if safeties_only and te and te[1] >= 0.15 else roles["wr"].get(opp)
        if not pick:
            return None
        return f"Helps {pick[0]} ({pick[1] * 100:.0f}% of {opp} targets): {with_line(pick[0], 'reception_yds')}."
    rb = roles["rb"].get(opp)
    if not rb:
        return None
    return f"Helps {rb[0]} ({rb[1] * 100:.0f}% of {opp} carries): {with_line(rb[0], 'rush_yds')}."


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
                note = weather_note("mlb", wx.get("wind_mph"), wx.get("precip_pct"), wx.get("temp_f"), eff,
                                    wx.get("wind_gust_mph"), _rain(wx))
                txt = weather_text(wx)
                flags.append({"kind": "weather", "tone": note["tone"] if note else "neutral", "text": txt,
                              "why": note["why"] if note else None, "alert": note})
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
    starters = _safe("nfl starters", nfl_starters, {})
    roles = _safe("nfl roles", _nfl_roles, {"qb": {}, "wr": {}, "te": {}, "rb": {}, "sacks": {}})
    if not inj.empty:
        inj = inj.assign(abbr=inj["team"].map(lambda t: abbr.get(t, t)))
    from app.data.loader import get_props_data
    props = _safe("nfl props", lambda: get_props_data("nfl"), pd.DataFrame())
    if not props.empty:
        props = props.assign(_k=props["Player"].map(_key))

    def prop_line(name: str, market: str) -> Optional[float]:
        if props.empty:
            return None
        rows = props[(props["_k"] == _key(name)) & (props["market"] == market)]
        return None if rows.empty else float(rows["Line"].median())

    ordinal = _ordinal

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
        for team, opp in ((aa, ha), (ha, aa)):
            if not team or inj.empty:
                continue
            for grp in trench_groups(inj, team, starters):
                n = len(grp["out"])
                parts = []
                if grp["out"]:
                    parts.append(", ".join(grp["out"]) + " out")
                if grp["questionable"]:
                    parts.append(", ".join(grp["questionable"]) + " questionable")
                safeties = all(x.split("(")[-1].rstrip(")") in {"S", "SS", "FS"} for x in grp["out"] + grp["questionable"])
                flags.append({"kind": grp["label"].lower(), "tone": "bad" if n else "warn",
                              "text": f"{team}: " + "; ".join(parts),
                              "why": _if_they_sit(n, _safe("unit note", lambda g=grp, t=team, o=opp, sf=safeties:
                                                               _unit_note(g["unit"], t, o, roles, prop_line, sf), None))})
        for g in mism:
            if {g.get("offense_team"), g.get("defense_team")} == {ha, aa}:
                flags.append({"kind": "mismatch", "tone": "good",
                              "text": f"{g['offense_team']} {g['off_label']} ({ordinal(int(g['offense_rank']))}) vs "
                                      f"{g['defense_team']} {g['def_label']} ({ordinal(int(g['defense_rank']))})"})
        wx = next((w for w in weather if w.get("home_team") == ha), None)
        if wx and wx.get("roof") in (None, "outdoor", "open"):
            txt = weather_text(wx)
            note = weather_note("nfl", wx.get("wind_mph"), wx.get("precip_pct"), wx.get("temp_f"),
                                gust=wx.get("wind_gust_mph"), rain=_rain(wx))
            flags.append({"kind": "weather", "tone": note["tone"] if note else "neutral", "text": txt,
                          "why": note["why"] if note else None, "alert": note})
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


def _weather_changes(games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One alert per slate game whose weather flag has something to say:
    the ones strong enough to matter first, then by start time (games arrive
    sorted, and the sort is stable)."""
    out = []
    for g in games:
        for f in g["flags"]:
            if f.get("kind") == "weather" and f.get("alert"):
                out.append({"kind": "weather", "sport": g["sport"], "time": None,
                            "tag": f["alert"]["tag"], "tone": f["alert"]["tone"],
                            "title": f"{_nick(g['away_team'])} @ {_nick(g['home_team'])} · {f['text']}",
                            "detail": f["alert"]["why"]})
    return sorted(out, key=lambda c: c["tone"] != "warn")


@ttl_cache(300)
def get_briefing() -> Dict[str, Any]:
    from app.data import mlb
    report = _safe("pitcher report", mlb.get_pitcher_daily_report, {"pitchers": []})
    nfl_events = _safe("nfl events", lambda: _events("nfl"), [])
    games = (_safe("mlb slate", lambda: _mlb_cards(_events("mlb"), report), [])
             + _safe("nfl slate", lambda: _nfl_cards(nfl_events), []))
    games.sort(key=lambda g: g["commence_time"])
    usage = _safe("usage", lambda: _usage(nfl_events), [])
    _safe("usage flags", lambda: _attach_usage(games, usage), None)
    changes = (_safe("injuries", _injury_changes, []) + _weather_changes(games) + usage
               + _safe("lineups", lambda: _lineup_changes(report), []) + _safe("moves", _moves, []))
    changes.sort(key=lambda c: c.get("time") or "", reverse=True)
    for g in games:
        for f in g["flags"]:
            f.pop("alert", None)
    return {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "changes": changes, "games": games}
