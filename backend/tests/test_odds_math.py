import math

from app.odds_math import (
    devig_two_way, ev_per_unit, implied_prob, is_price, median_price,
    prob_to_american, shrink_toward, to_decimal,
)


def close(a, b, tol=1e-3):
    return abs(a - b) <= tol


def test_implied_and_decimal():
    assert close(implied_prob(-110), 0.5238)
    assert close(implied_prob(130), 0.4348)
    assert close(to_decimal(-110), 1.9091)
    assert close(to_decimal(130), 2.30)


def test_is_price_rejects_non_prices():
    assert not is_price(None)
    assert not is_price(float("nan"))
    assert not is_price(50)
    assert is_price(-100) and is_price(100)


def test_devig_brunson_example():
    # The worked example from the explainer: -118/-102 -> ~51.7% fair over.
    p = devig_two_way(-118, -102)
    assert close(p, 0.5174)
    # FanDuel +112 at that fair chance is ~+9.7% EV.
    assert close(ev_per_unit(p, 112), 0.0969, 1e-3)


def test_devig_requires_both_sides_and_margin():
    assert devig_two_way(-110, None) is None
    # +150/+150 sums below 1 -- not one market, so no fair price.
    assert devig_two_way(150, 150) is None


def test_outlier_cases_from_explainer():
    # Case A: consensus -135/+105 -> fair over ~54%, so -118 is ~breakeven.
    pa = devig_two_way(-135, 105)
    assert close(pa, 0.5405)
    assert abs(ev_per_unit(pa, -118)) < 0.005
    # Case B: consensus -135/+115 -> fair ~55.3%, -118 is ~+2%.
    pb = devig_two_way(-135, 115)
    assert close(pb, 0.5526)
    assert close(ev_per_unit(pb, -118), 0.021, 2e-3)


def test_prob_to_american_round_trip():
    assert prob_to_american(0.5) == 100
    assert prob_to_american(0.6) == -150
    assert prob_to_american(0.25) == 300
    assert prob_to_american(0) is None and prob_to_american(1) is None


def test_median_price_crosses_even_money():
    # Averaging -105 and +105 as numbers gives 0; in probability space it's ~even.
    assert median_price([-105, 105]) in (100, -100)
    assert median_price([-130, -132, -135, -138, -140]) == -135
    assert median_price([]) is None


def test_shrinkage():
    # 3-for-4 on a 30% rung with 15 games of prior -> ~39%, not 75%.
    assert close(shrink_toward(3, 4, 0.30, 15), 0.3947)
    assert shrink_toward(0, 0, 0.3, 15) == 0.3
