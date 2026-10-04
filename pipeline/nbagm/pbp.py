"""Per-player on-court accounting from play-by-play (playbyplayv3) + rotations (gamerotation).

Several doc 02/03 denominators are "... while this player was on the floor"
(team missed FGA, opponent rebounds, defensive possessions, ...). No public
endpoint publishes those directly, so they are counted here event by event.

Who is on the floor comes from gamerotation stints (tenths of a second of game
time). Events that share a timestamp with a substitution (free throws around a
sub, mostly) are assigned using the play-by-play order: an event listed after
that team's substitution action at the same clock belongs to the new lineup.

Possessions use the standard estimate FGA - OREB + TOV + 0.44*FTA, applied to
the on-court counts (offense: own team's events; defense: the opponent's).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

ON_COURT_FIELDS = (
    "team_fga", "team_missed_fga", "team_fta", "team_oreb", "team_dreb", "team_tov",
    "opp_fga", "opp_missed_fga", "opp_fta", "opp_oreb", "opp_dreb", "opp_tov",
    "opp_missed_final_ft",
)

_CLOCK = re.compile(r"PT(\d+)M(\d+(?:\.\d+)?)S")
_FT_OF = re.compile(r"Free Throw (\d+) of (\d+)$")


def _int(x):
    """int for real ids; None for missing values (None, NaN, '', 0)."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or x == "":
        return None
    v = int(x)
    return v or None


def period_start(period):
    return (period - 1) * 7200 if period <= 4 else 28800 + (period - 5) * 3000


def period_end(period):
    return period_start(period) + (7200 if period <= 4 else 3000)


def clock_tenths(clock, period):
    """Elapsed game time in integer tenths of a second for a v3 clock string."""
    m = _CLOCK.fullmatch(str(clock))
    if not m:
        raise ValueError(f"unparseable clock {clock!r}")
    remaining = int(m.group(1)) * 60 + float(m.group(2))
    return period_end(period) - int(round(remaining * 10))


@dataclass
class GameAccount:
    game_id: str
    # (player_id, team_id) -> field -> count
    on_court: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    # player_id -> turnover subType -> count
    turnovers_by_type: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    events_total: int = 0
    events_unresolved: int = 0


@dataclass(frozen=True)
class Stint:
    player_id: int
    team_id: int
    t_in: int
    t_out: int


def stints_from_rotation(rotation_frames):
    out = []
    for df in rotation_frames.values():
        for row in df.itertuples(index=False):
            out.append(Stint(int(row.PERSON_ID), int(row.TEAM_ID),
                             int(round(float(row.IN_TIME_REAL))), int(round(float(row.OUT_TIME_REAL)))))
    return out


def _on_court(stint, t, period, after_sub):
    ps, pe = period_start(period), period_end(period)
    if abs(stint.t_in - t) <= 1:
        return abs(t - ps) <= 1 or (abs(t - pe) > 1 and after_sub)
    if abs(stint.t_out - t) <= 1:
        return abs(t - pe) <= 1 or (abs(t - ps) > 1 and not after_sub)
    return stint.t_in < t < stint.t_out


def is_made_ft(row):
    if row["shotResult"] in ("Made", "Missed"):
        return row["shotResult"] == "Made"
    return not str(row["description"]).upper().startswith("MISS")


def is_reboundable_final_ft(sub_type):
    """Last free throw of a regular trip (e.g. '2 of 2'): the only FT whose miss is live.
    Technical, flagrant and clear-path free throws do not end in a rebound."""
    m = _FT_OF.search(str(sub_type))
    return bool(m) and "Flagrant" not in str(sub_type) and "Clear Path" not in str(sub_type) \
        and m.group(1) == m.group(2)


def account_game(game_id, pbp, stints, box_player_ids):
    """Count on-court team/opponent events for every player in one game."""
    acc = GameAccount(game_id)
    by_team = defaultdict(list)
    for s in stints:
        by_team[s.team_id].append(s)
    teams = list(by_team)
    if len(teams) != 2:
        raise ValueError(f"game {game_id}: rotation has {len(teams)} teams")
    other = {teams[0]: teams[1], teams[1]: teams[0]}

    # Substitution actions by (team, period, clock) -> earliest row position
    pbp = pbp.reset_index(drop=True)
    sub_pos = {}
    for pos, row in pbp.iterrows():
        if row["actionType"] == "Substitution" and _int(row["teamId"]):
            key = (_int(row["teamId"]), int(row["period"]), row["clock"])
            sub_pos.setdefault(key, pos)

    lineup_cache = {}

    def lineup(team, pos, row):
        period = int(row["period"])
        t = clock_tenths(row["clock"], period)
        sp = sub_pos.get((team, period, row["clock"]))
        after = sp is not None and sp < pos
        key = (team, t, period, after)
        if key not in lineup_cache:
            players = [s.player_id for s in by_team[team] if _on_court(s, t, period, after)]
            if len(players) != 5:
                alt = [s.player_id for s in by_team[team] if _on_court(s, t, period, not after)]
                players = alt if len(alt) == 5 else None
            lineup_cache[key] = players
        return lineup_cache[key]

    def credit(pos, row, team, team_field, opp_field, amount=1.0):
        acc.events_total += 1
        own, opp = lineup(team, pos, row), lineup(other[team], pos, row)
        if own is None or opp is None:
            acc.events_unresolved += 1
            return
        if team_field:
            for p in own:
                acc.on_court[(p, team)][team_field] += amount
        if opp_field:
            for p in opp:
                acc.on_court[(p, other[team])][opp_field] += amount

    last_miss_team = None
    for pos, row in pbp.iterrows():
        action = row["actionType"]
        team = _int(row["teamId"])
        if team is not None and team not in other:
            continue
        person = _int(row["personId"]) or 0
        if team is None and action in ("Made Shot", "Missed Shot", "Free Throw"):
            continue

        if action in ("Made Shot", "Missed Shot") and _int(row["isFieldGoal"]) == 1:
            credit(pos, row, team, "team_fga", "opp_fga")
            if action == "Missed Shot":
                credit(pos, row, team, "team_missed_fga", "opp_missed_fga")
                last_miss_team = team
            else:
                last_miss_team = None
        elif action == "Free Throw":
            credit(pos, row, team, "team_fta", "opp_fta")
            if is_made_ft(row):
                last_miss_team = None
            else:
                last_miss_team = team
                if is_reboundable_final_ft(row["subType"]):
                    # opp_missed_final_ft is credited to the defending (rebounding) side
                    credit(pos, row, team, None, "opp_missed_final_ft")
        elif action == "Rebound":
            if person in box_player_ids and last_miss_team is not None and team is not None:
                if team == last_miss_team:
                    credit(pos, row, team, "team_oreb", "opp_oreb")
                else:
                    credit(pos, row, team, "team_dreb", "opp_dreb")
            last_miss_team = None
        elif action == "Turnover":
            sub = str(row["subType"] or "")
            if "No Turnover" in sub or team is None:
                continue
            credit(pos, row, team, "team_tov", "opp_tov")
            if person in box_player_ids:
                acc.turnovers_by_type[person][sub] += 1
            last_miss_team = None
    return acc


def possessions(counts, side):
    """Standard possession estimate applied to on-court counts."""
    p = "team" if side == "off" else "opp"
    return (np.asarray(counts[f"{p}_fga"]) - np.asarray(counts[f"{p}_oreb"])
            + np.asarray(counts[f"{p}_tov"]) + 0.44 * np.asarray(counts[f"{p}_fta"]))
