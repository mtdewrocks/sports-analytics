"""Top-picks emails: timing window, grouping, once-only, test-address only."""
import pandas as pd

from app import pick_emails as P
from app.config import settings
from app.database import Base, engine, SessionLocal


def _games(start):
    return [{"start": start, "title": "NYK @ BOS", "bets": ["Brunson OVER 25.5 Points"], "watch": []},
            {"start": start, "title": "LAL @ GSW", "bets": [], "watch": []},
            {"start": start + pd.Timedelta(hours=2), "title": "DEN @ PHX", "bets": ["Jokic OVER 11.5 Rebounds"], "watch": []}]


def test_sends_each_window_once_to_test_address_only(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal(); db.query(P.PickEmailLog).delete(); db.commit(); db.close()
    start = pd.Timestamp("2026-11-14T00:30:00Z")
    monkeypatch.setitem(P.SOURCES, "nba", lambda: _games(start))
    sent = []
    monkeypatch.setattr(P, "send_email", lambda to, subj, body: sent.append((to, subj, body)) or True)
    monkeypatch.setattr(settings, "PICK_EMAILS_TEST_TO", "tester@example.com")

    assert P.run_once(start - pd.Timedelta(minutes=45), ("nba",)) == []          # too early
    out = P.run_once(start - pd.Timedelta(minutes=29), ("nba",))
    assert len(out) == 1 and len(sent) == 1 and sent[0][0] == "tester@example.com"
    assert "2 games" in sent[0][1] and "NYK @ BOS" in sent[0][2] and "nothing clears the bar" in sent[0][2]
    assert "★ Brunson" in sent[0][2] and "DEN @ PHX" not in sent[0][2]                                          # later window, separate email
    assert P.run_once(start - pd.Timedelta(minutes=24), ("nba",)) == []          # already sent
    assert P.run_once(start + pd.Timedelta(hours=2) - pd.Timedelta(minutes=8), ("nba",)) == []  # too late: skip
    assert len(sent) == 1


def test_nothing_sends_without_a_test_address(monkeypatch):
    monkeypatch.setattr(settings, "PICK_EMAILS_TEST_TO", "")
    monkeypatch.setitem(P.SOURCES, "nba", lambda: (_ for _ in ()).throw(AssertionError("should not load")))
    assert P.run_once(pd.Timestamp.now(tz="UTC"), ("nba",)) == []


def test_hit_text():
    assert P.hit_text([10, 20, 30, 5, None], 15.5, "over", 10) == "L10 2/4"
    assert P.hit_text([1, 2, 3, 4, 5, 6, 7], 3.5, "under", 5) == "L5 1/5"
    assert P.hit_text([], 3.5, "under", 5) == ""


def test_nba_reasons_only_those_backing_the_pick():
    import pandas as pd
    from app import nba_reasons as RS
    base = pd.DataFrame({"3PM": [2.0]}).reindex(columns=["PTS", "REB", "AST", "3PM", "BLK", "STL", "TOV"]).fillna(1.0)
    zero = base * 0
    eff = {k: zero.copy() for k in RS.FACTORS}
    eff["matchup"].loc[0, "3PM"] = 0.3       # opponent adds threes
    eff["rest"].loc[0, "3PM"] = -0.2         # back-to-back takes some away
    eff["_base"] = base
    row = pd.Series({"Opponent": "IND", "TEAM": "NYK", "Opp_3PM_rel": 1.14, "is_b2b": 1, "ew": 30.0,
                     "3PM_roll5": 2.0, "3PM_oly10": 2.0})
    slate = pd.DataFrame({"TEAM": ["NYK"], "out": [False], "played_last": [True], "PLAYER": ["x"]})
    over = RS.reasons_for(0, row, "threes", "over", eff, slate, 30.0)
    under = RS.reasons_for(0, row, "threes", "under", eff, slate, 30.0)
    assert over == ["IND allows 14% more threes than average (+.30)"]
    assert under == ["second night of a back-to-back (-.20)"]


def test_nfl_reasons_follow_the_pick():
    from app import nfl_reasons as RS
    p = {"team": "ATL", "opponent": "KC", "position": "RB",
         "why": {"script_shift": 0.04, "team_spread": -6.5, "implied_pts": 27.0,
                 "opp_rel": {"rush_yds": 0.85, "rec": 1.2}, "sim_carries": 14.0, "ew_carries": 18.0,
                 "sim_targets": 3.0, "ew_targets": 3.1}}
    under_rush = RS.reasons_for(p, "rush_yds", "under", n=3)
    assert len(under_rush) == 3 and any("carries" in r for r in under_rush) and any(r.startswith("KC allows 15% fewer rushing yards") for r in under_rush)
    assert any("throwing on 4% more" in r for r in under_rush)          # more passing -> fewer rush yards
    over_rec = RS.reasons_for(p, "receptions", "over")
    assert any("throwing on 4% more" in r for r in over_rec) and any("20% more catches to RBs" in r for r in over_rec)
    assert RS.reasons_for(p, "receptions", "under") == []
    assert RS.reasons_for({}, "receptions", "over") == []


def test_nfl_qb_change_reason():
    from app import nfl_reasons as RS
    p = {"team": "MIN", "opponent": "GB", "position": "WR",
         "why": {"qb_change": {"now": "Carson Wentz", "usual": "Kyler Murray", "now_ypa": 5.6, "usual_ypa": 6.6,
                               "usual_status": "Out"}}}
    assert RS.reasons_for(p, "reception_yds", "under") == [
        "Carson Wentz starting for Kyler Murray (out): 5.6 yds per attempt this season vs 6.6"]
    assert RS.reasons_for(p, "reception_yds", "over") == []
