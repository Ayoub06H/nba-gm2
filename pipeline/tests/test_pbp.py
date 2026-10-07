"""Lineup reconstruction and on-court counting, using the real stats.nba.com v3 shapes
(as printed by inspect_cache.py from a real 2025-26 game)."""

import pandas as pd
import pytest

from nbagm.pbp import Stint, account_game, clock_tenths, is_reboundable_final_ft, possessions

A, B = 1610612701, 1610612702


def box(players):
    """players: (personId, teamId, familyName, starter, minutes)"""
    return pd.DataFrame([{"personId": p, "teamId": t, "familyName": n,
                          "position": "F" if s else "", "minutes": m}
                         for p, t, n, s, m in players])


def act(n, clock, period, team, person, action_type, sub_type="", desc="", result="", fg=0, name=""):
    return {"actionNumber": n, "clock": clock, "period": period, "teamId": team, "personId": person,
            "playerName": name, "actionType": action_type, "subType": sub_type, "description": desc,
            "shotResult": result, "isFieldGoal": fg}


def period_marks(period):
    return (act(0, "PT12M00.00S", period, 0, 0, "period", "start"),
            act(999, "PT00M00.00S", period, 0, 0, "period", "end"))


STANDARD_BOX = box(
    [(100 + k, A, f"A{k}", k <= 5, "24:00") for k in range(1, 7)]
    + [(200 + k, B, f"B{k}", k <= 5, "24:00") for k in range(1, 7)])


@pytest.fixture
def game():
    s1, e1 = period_marks(1)
    s2, e2 = period_marks(2)
    pbp = pd.DataFrame([
        s1,
        act(2, "PT11M00.00S", 1, A, 101, "Missed Shot", "Jump Shot", "MISS A1 Jump Shot", "Missed", 1),
        act(3, "PT11M00.00S", 1, A, 102, "Rebound", "Unknown", "A2 REBOUND (Off:1 Def:0)"),
        act(4, "PT10M50.00S", 1, A, 103, "Made Shot", "Layup", "A3 Layup", "Made", 1),
        act(5, "PT10M00.00S", 1, B, 201, "Turnover", "Bad Pass", "B1 Bad Pass Turnover"),
        act(5, "PT10M00.00S", 1, A, 104, "", "", "A4 STEAL (1 STL)"),
        act(6, "PT07M00.00S", 1, B, 202, "Foul", "Shooting", "B2 S.FOUL"),
        act(7, "PT07M00.00S", 1, A, 105, "Free Throw", "Free Throw 1 of 2", "A5 Free Throw 1 of 2 (1 PTS)"),
        act(8, "PT07M00.00S", 1, B, 205, "Substitution", "", "SUB: B6 FOR B5"),
        act(9, "PT07M00.00S", 1, A, 105, "Free Throw", "Free Throw 2 of 2", "MISS A5 Free Throw 2 of 2"),
        act(10, "PT07M00.00S", 1, B, 203, "Rebound", "Unknown", "B3 REBOUND (Off:0 Def:1)"),
        act(11, "PT05M00.00S", 1, B, 204, "Missed Shot", "Jump Shot", "MISS B4 Jump Shot", "Missed", 1),
        act(12, "PT05M00.00S", 1, 0, A, "Rebound", "Unknown", "Team Rebound"),
        act(13, "PT04M00.00S", 1, 0, B, "Turnover", "Shot Clock Turnover", "Team Turnover: Shot Clock"),
        act(14, "PT03M00.00S", 1, 0, A, "Timeout", "Regular", "Timeout: Regular"),
        e1,
        # Period 2: A silently swapped A5 for A6 at the break; nothing logs it.
        s2,
        act(20, "PT11M00.00S", 2, A, 106, "Made Shot", "Dunk", "A6 Dunk", "Made", 1),
        act(21, "PT10M30.00S", 2, B, 201, "Missed Shot", "Jump Shot", "MISS B1 Jump Shot", "Missed", 1),
        act(22, "PT10M30.00S", 2, A, 101, "Rebound", "Unknown", "A1 REBOUND"),
        act(23, "PT10M00.00S", 2, A, 102, "Turnover", "Lost Ball", "A2 Lost Ball Turnover"),
        act(24, "PT09M50.00S", 2, A, 103, "Foul", "Personal", "A3 P.FOUL"),
        act(25, "PT09M40.00S", 2, A, 104, "Missed Shot", "Jump Shot", "MISS A4 Jump Shot", "Missed", 1),
        act(26, "PT09M40.00S", 2, B, 202, "Rebound", "Unknown", "B2 REBOUND"),
        act(27, "PT09M00.00S", 2, B, 203, "Made Shot", "Layup", "B3 Layup", "Made", 1),
        act(28, "PT08M00.00S", 2, B, 204, "Turnover", "Traveling", "B4 Traveling Turnover"),
        act(29, "PT07M00.00S", 2, B, 206, "Foul", "Personal", "B6 P.FOUL"),
        e2,
    ])
    return account_game("g1", pbp, STANDARD_BOX)


def c(acc, pid, team):
    return dict(acc.on_court[(pid, team)])


def test_clock_conversion():
    assert clock_tenths("PT12M00.00S", 1) == 0
    assert clock_tenths("PT07M00.00S", 1) == 3000
    assert clock_tenths("PT00M00.00S", 4) == 28800
    assert clock_tenths("PT05M00.00S", 5) == 28800


def test_offense_counts_follow_the_lineup_across_a_silent_period_change(game):
    assert c(game, 101, A)["team_fga"] == 4
    assert c(game, 105, A)["team_fga"] == 2      # benched at the break
    assert c(game, 106, A)["team_fga"] == 2      # came in at the break
    assert c(game, 101, A)["team_oreb"] == 1


def test_substitution_between_free_throws(game):
    for p in (201, 202, 203, 204):
        assert c(game, p, B)["opp_fta"] == 2
    assert c(game, 205, B)["opp_fta"] == 1       # first FT, before the sub
    assert c(game, 206, B)["opp_fta"] == 1       # second FT, after it
    assert c(game, 206, B)["opp_missed_final_ft"] == 1
    assert "opp_missed_final_ft" not in c(game, 205, B)


def test_team_events_with_team_id_zero(game):
    # team turnover (teamId 0, personId = team) counts; team rebound is not a player rebound
    assert c(game, 201, B)["team_tov"] == 3
    assert c(game, 205, B)["team_tov"] == 1
    assert c(game, 206, B)["team_tov"] == 2
    assert c(game, 201, B)["team_dreb"] == 2
    assert c(game, 101, A).get("team_oreb") == 1


def test_seconds_on_court(game):
    assert game.seconds_on[101] == pytest.approx(1440)
    assert game.seconds_on[105] == pytest.approx(720)
    assert game.seconds_on[106] == pytest.approx(720)
    assert game.seconds_on[205] == pytest.approx(300)
    assert game.seconds_on[206] == pytest.approx(420 + 720)


def test_turnover_types_and_diagnostics(game):
    assert game.turnovers_by_type[201]["Bad Pass"] == 1
    assert game.turnovers_by_type[102]["Lost Ball"] == 1
    assert game.events_unresolved == 0
    assert game.diagnostics["period_starters_inferred"] == 2
    assert game.diagnostics.get("period_starters_unresolved", 0) == 0
    assert game.diagnostics.get("actor_not_in_tracked_lineup", 0) == 0


def test_same_surname_is_resolved_by_who_appears_next():
    bx = box([(100 + k, A, f"A{k}", k <= 5, "10:00") for k in range(1, 6)]
             + [(107, A, "Williams", False, "5:00"), (108, A, "Williams", False, "5:00")]
             + [(200 + k, B, f"B{k}", True, "10:00") for k in range(1, 6)])
    s, e = period_marks(1)
    pbp = pd.DataFrame([
        s,
        act(2, "PT06M00.00S", 1, A, 101, "Substitution", "", "SUB: Williams FOR A1"),
        act(3, "PT05M00.00S", 1, A, 108, "Made Shot", "Layup", "Williams Layup", "Made", 1),
        e,
    ])
    acc = account_game("g2", pbp, bx)
    assert c(acc, 108, A)["team_fga"] == 1
    assert (107, A) not in acc.on_court
    assert acc.diagnostics["subs_resolved_by_lookahead"] == 1


def test_quiet_starter_is_completed_from_previous_period():
    s1, e1 = period_marks(1)
    s2, e2 = period_marks(2)
    actions = [s1, e1, s2]
    # Period 2: same lineups, but A5 and B5 never act.
    for k in range(1, 5):
        actions.append(act(10 + k, f"PT{11 - k:02d}M00.00S", 2, A, 100 + k, "Foul", "Personal", "foul"))
        actions.append(act(20 + k, f"PT{11 - k:02d}M00.00S", 2, B, 200 + k, "Foul", "Personal", "foul"))
    actions.append(act(30, "PT02M00.00S", 2, A, 101, "Made Shot", "Layup", "A1 Layup", "Made", 1))
    actions.append(e2)
    acc = account_game("g3", pd.DataFrame(actions), STANDARD_BOX)
    assert c(acc, 105, A)["team_fga"] == 1
    assert acc.diagnostics["period_starters_completed_from_previous_period"] == 2
    assert acc.events_unresolved == 0


def test_rotation_data_is_used_for_period_starters_when_present():
    s1, e1 = period_marks(1)
    s2, e2 = period_marks(2)
    pbp = pd.DataFrame([s1, e1, s2,
                        act(2, "PT06M00.00S", 2, A, 101, "Made Shot", "Layup", "A1 Layup", "Made", 1), e2])
    stints = [Stint(p, A, 7200, 14400) for p in (101, 102, 103, 104, 106)]
    stints += [Stint(p, B, 7200, 14400) for p in (201, 202, 203, 204, 205)]
    acc = account_game("g4", pbp, STANDARD_BOX, stints)
    assert c(acc, 106, A)["team_fga"] == 1 and (105, A) not in acc.on_court
    assert acc.diagnostics.get("period_starters_inferred", 0) == 0


def test_unresolvable_lineup_skips_events_instead_of_guessing():
    s1, e1 = period_marks(1)
    s2, e2 = period_marks(2)
    pbp = pd.DataFrame([s1,
                        act(2, "PT06M00.00S", 1, A, 101, "Substitution", "", "SUB: Nobody FOR A1"),
                        act(3, "PT05M00.00S", 1, A, 102, "Made Shot", "Layup", "A2 Layup", "Made", 1),
                        e1])
    acc = account_game("g5", pbp, STANDARD_BOX)
    assert acc.diagnostics["subs_unresolved"] == 1
    assert acc.events_unresolved == 1          # only 4 of 5 ever identified: never guessed
    assert (102, A) not in acc.on_court


def test_possession_estimate():
    counts = {"team_fga": [10], "team_oreb": [2], "team_tov": [3], "team_fta": [5]}
    assert possessions(counts, "off")[0] == pytest.approx(10 - 2 + 3 + 2.2)


@pytest.mark.parametrize("sub_type,expected", [
    ("Free Throw 2 of 2", True), ("Free Throw 1 of 2", False), ("Free Throw 1 of 1", True),
    ("Free Throw Technical", False), ("Free Throw Flagrant 2 of 2", False),
    ("Free Throw Clear Path 2 of 2", False),
])
def test_reboundable_final_ft(sub_type, expected):
    assert is_reboundable_final_ft(sub_type) is expected


def test_lineup_recovers_once_the_unknown_substitute_shows_up():
    s1, e1 = period_marks(1)
    pbp = pd.DataFrame([
        s1,
        act(2, "PT06M00.00S", 1, A, 101, "Substitution", "", "SUB: Nobody FOR A1"),
        act(3, "PT05M50.00S", 1, A, 102, "Made Shot", "Layup", "A2 Layup", "Made", 1),   # unknown 5th
        act(4, "PT05M00.00S", 1, A, 106, "Foul", "Personal", "A6 P.FOUL"),               # there he is
        act(5, "PT04M00.00S", 1, A, 103, "Made Shot", "Layup", "A3 Layup", "Made", 1),
        e1,
    ])
    acc = account_game("g6", pbp, STANDARD_BOX)
    assert acc.diagnostics["subs_unresolved"] == 1
    assert acc.diagnostics["lineups_recovered_mid_period"] >= 1
    # the shot at 5:50 is attributed once 106 is identified as the fifth player
    assert c(acc, 106, A)["team_fga"] == 2
    assert acc.events_unresolved == 0
    assert any("incoming name not found" in e for e in acc.examples)


def test_initial_name_form_matches():
    bx = box([(100 + k, A, f"A{k}", k <= 5, "10:00") for k in range(1, 6)]
             + [(107, A, "Williams", False, "5:00")]
             + [(200 + k, B, f"B{k}", True, "10:00") for k in range(1, 6)])
    bx["nameI"] = [f"X. {n}" for n in bx["familyName"]]
    s, e = period_marks(1)
    pbp = pd.DataFrame([s, act(2, "PT06M00.00S", 1, A, 101, "Substitution", "", "SUB: X. Williams FOR A1"),
                        act(3, "PT05M00.00S", 1, A, 107, "Made Shot", "Layup", "Layup", "Made", 1), e])
    acc = account_game("g7", pbp, bx)
    assert acc.diagnostics.get("subs_unresolved", 0) == 0
    assert c(acc, 107, A)["team_fga"] == 1
