import numpy as np
import pandas as pd
import pytest

from nbagm import derive


def test_runs_test_matches_textbook_values():
    # 10 makes, 10 misses perfectly alternating: 20 runs, mu = 11, var = 90/19
    alt = [1, 0] * 10
    assert derive.runs_test_z(alt) == pytest.approx((20 - 11) / np.sqrt(90 / 19))
    # two long runs: fewer runs than chance -> negative z
    assert derive.runs_test_z([1] * 10 + [0] * 10) < -3


def test_runs_test_degenerate_sequences_are_zero():
    assert derive.runs_test_z([]) == 0.0
    assert derive.runs_test_z([1, 1, 1]) == 0.0
    assert derive.runs_test_z([0]) == 0.0


def test_streaky_value_is_negated_runs_z():
    shots = pd.DataFrame({
        "PLAYER_ID": [7] * 20, "GAME_DATE": ["2025-11-01"] * 20, "GAME_ID": ["g"] * 20,
        "GAME_EVENT_ID": range(20), "SHOT_MADE_FLAG": [1] * 10 + [0] * 10})
    value, z = derive.streaky(shots, [7, 8])
    assert value[0] > 3 and z[0] == value[0]
    assert value[1] == 0.0                        # no shots: no claim either way


@pytest.mark.parametrize("z,tier", [(-2.5, -2), (-2.0, -2), (-1.5, -1), (-0.99, 0), (0, 0),
                                    (0.99, 0), (1.0, 1), (1.99, 1), (2.0, 2), (5, 2)])
def test_trait_tiers(z, tier):
    assert derive.trait_tier([z])[0] == tier


def test_offensive_load_matches_hand_computation():
    inputs = pd.DataFrame({"OFF_POSS": [100.0], "AST": [8.0], "PTS": [25.0], "TOV": [3.0],
                           "FG3A": [6.0], "FG3M": [2.4], "FGA": [20.0], "FTA": [6.0]})
    load, poss = derive.offensive_load(inputs)
    prof = (2 / (1 + np.exp(-6.0)) - 1) * 0.4
    bc = 8 * 0.1843 + 28 * 0.0969 - 2.3021 * prof + 0.0582 * (8 * 28 * prof) - 1.1942
    expected = (8 - 0.38 * bc) * 0.75 + 20 + 6 * 0.44 + bc + 3
    assert load[0] == pytest.approx(expected)
    assert poss[0] == 100.0


def test_percentile_orientation():
    p = derive.league_percentile([0.1, 0.2, 0.3], higher_is_better=False)
    assert p[0] > p[1] > p[2]
    assert derive.league_percentile([5, 5])[0] == pytest.approx(0.5)


def test_wingspan_regression_uses_only_players_with_both():
    roster = pd.DataFrame({"player_id": [1, 2, 3, 4], "height_in": [74.0, 78.0, 82.0, 80.0]})
    combine = pd.DataFrame({"wingspan_in": [78.0, 82.0, 86.0]},
                           index=pd.Index([1, 2, 3], name="player_id"))
    w, imputed, (a, b, n) = derive.wingspans(roster, combine)
    assert n == 3 and b == pytest.approx(1.0) and a == pytest.approx(4.0)
    assert w[4] == pytest.approx(84.0) and bool(imputed[4]) and not bool(imputed[1])


def test_depth_chart_starters_by_games_started_then_minutes():
    roster = pd.DataFrame({"player_id": range(1, 8), "team_id": [9] * 7})
    usage = pd.DataFrame({"player_id": range(1, 8), "team_id": [9] * 7,
                          "games_played": [80, 80, 80, 80, 80, 80, 10],
                          "games_started": [80, 70, 60, 50, 0, 40, 10],
                          "minutes": [2800, 2400, 2000, 1800, 2600, 1500, 100]})
    d = derive.depth_chart(roster, usage).set_index("player_id")["depth_rank"]
    assert list(d.sort_values().index[:5]) == [1, 2, 3, 4, 6]
    assert d[5] == 6 and d[7] == 7          # bench ordered by minutes per game


def test_every_locked_field_is_declared_once():
    attrs = [a.key for a in derive.ATTRIBUTES]
    tends = [t.key for t in derive.TENDENCIES]
    assert len(attrs) == len(set(attrs)) == 28     # doc 01: 28 rated attributes
    assert len(tends) == len(set(tends)) == 21     # doc 03: 24 listed, 3 parked
    assert {t.key for t in derive.TRAITS} == set(derive.TIER_NAMES)


def test_zscore_of_a_constant_component_is_zero_not_nan():
    z = derive._zscore([0.3, 0.3 + 1e-18, 0.3, np.nan])
    assert list(z[:3]) == [0.0, 0.0, 0.0] and np.isnan(z[3])
