import pandas as pd
import pytest

from nbagm.pbp import Stint, account_game, clock_tenths, is_reboundable_final_ft, possessions

A, B = 1, 2


def action(n, clock, team, person, action_type, sub_type="", desc="", result=None, fg=0):
    return {"actionNumber": n, "clock": clock, "period": 1, "teamId": team, "personId": person,
            "actionType": action_type, "subType": sub_type, "description": desc,
            "shotResult": result, "isFieldGoal": fg}


@pytest.fixture
def game():
    stints = [Stint(p, A, 0, 7200) for p in (101, 102, 103, 104)]
    stints += [Stint(105, A, 0, 3000), Stint(106, A, 3000, 7200)]
    stints += [Stint(p, B, 0, 7200) for p in (201, 202, 203, 204, 205)]
    pbp = pd.DataFrame([
        action(1, "PT12M00.00S", None, 0, "period", "start"),
        action(2, "PT11M00.00S", A, 101, "Missed Shot", "Jump Shot", result="Missed", fg=1),
        action(3, "PT11M00.00S", A, 102, "Rebound", "offensive"),
        action(4, "PT10M50.00S", A, 103, "Made Shot", "Layup", result="Made", fg=1),
        action(5, "PT10M00.00S", B, 201, "Turnover", "Bad Pass"),
        action(6, "PT07M00.00S", B, 202, "Foul", "Shooting"),
        action(7, "PT07M00.00S", A, 105, "Free Throw", "Free Throw 1 of 2", "Smith Free Throw 1 of 2"),
        action(8, "PT07M00.00S", A, 105, "Substitution", "", "SUB: Jones FOR Smith"),
        action(9, "PT07M00.00S", A, 105, "Free Throw", "Free Throw 2 of 2", "MISS Smith Free Throw 2 of 2"),
        action(10, "PT07M00.00S", B, 203, "Rebound", "defensive"),
        action(11, "PT05M00.00S", B, 204, "Missed Shot", "Jump Shot", result="Missed", fg=1),
        action(12, "PT05M00.00S", A, 0, "Rebound", "team"),
        action(13, "PT00M00.00S", None, 0, "period", "end"),
    ])
    box_ids = {101, 102, 103, 104, 105, 106, 201, 202, 203, 204, 205}
    return account_game("g1", pbp, stints, box_ids)


def counts(acc, pid, team):
    return dict(acc.on_court[(pid, team)])


def test_clock_conversion():
    assert clock_tenths("PT12M00.00S", 1) == 0
    assert clock_tenths("PT07M00.00S", 1) == 3000
    assert clock_tenths("PT00M00.00S", 4) == 28800
    assert clock_tenths("PT05M00.00S", 5) == 28800


def test_offense_on_court_counts(game):
    for p in (101, 102, 103, 104):
        c = counts(game, p, A)
        assert c["team_fga"] == 2 and c["team_missed_fga"] == 1 and c["team_oreb"] == 1
        assert c["team_fta"] == 2
    assert counts(game, 105, A)["team_fta"] == 1      # free throw before the substitution
    assert counts(game, 106, A)["team_fta"] == 1      # free throw after it
    assert "team_fga" not in counts(game, 106, A)


def test_defense_on_court_counts(game):
    for p in (101, 102, 103, 104, 106):
        c = counts(game, p, A)
        assert c["opp_fga"] == 1 and c["opp_missed_fga"] == 1 and c["opp_dreb"] == 1
    assert counts(game, 105, A)["opp_tov"] == 1
    for p in (201, 202, 203, 204, 205):
        c = counts(game, p, B)
        assert c["opp_fga"] == 2 and c["opp_oreb"] == 1 and c["opp_fta"] == 2
        assert c["opp_missed_final_ft"] == 1
        assert c["team_tov"] == 1 and c["team_dreb"] == 1
        assert "team_oreb" not in c                     # team rebound is not a player rebound


def test_turnover_types_and_resolution(game):
    assert game.turnovers_by_type[201]["Bad Pass"] == 1
    assert game.events_unresolved == 0


def test_possession_estimate():
    c = {"team_fga": [10], "team_oreb": [2], "team_tov": [3], "team_fta": [5]}
    assert possessions(c, "off")[0] == pytest.approx(10 - 2 + 3 + 2.2)


@pytest.mark.parametrize("sub_type,expected", [
    ("Free Throw 2 of 2", True), ("Free Throw 1 of 2", False), ("Free Throw 1 of 1", True),
    ("Free Throw Technical", False), ("Free Throw Flagrant 2 of 2", False),
    ("Free Throw Clear Path 2 of 2", False),
])
def test_reboundable_final_ft(sub_type, expected):
    assert is_reboundable_final_ft(sub_type) is expected
