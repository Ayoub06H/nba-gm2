"""Assemble raw cached responses into the tables the derivations read.

Everything here is bookkeeping: selecting real columns, summing rows the API
splits by team, walking play-by-play, and joining sources on shared ids. No
formula from docs 02-04 lives in this module; those are in attributes.py,
tendencies.py and traits.py.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import plan
from .config import DURABILITY_SEASONS, SEASON
from .pbp import ON_COURT_FIELDS, PLAYER_EVENT_FIELDS, account_live, account_v3, possessions, \
    stint_possessions, stints_from_rotation

# Doc 11: the published label's index along the guard-to-center axis; a pair counts
# the same in either order.
POSITION_INDEX = {"G": 1, "G-F": 2, "F-G": 2, "F": 3, "F-C": 4, "C-F": 4, "C": 5}


@dataclass
class League:
    teams: pd.DataFrame
    roster: pd.DataFrame          # one row per rostered player
    inputs: pd.DataFrame          # index player_id: every real season count
    shots: pd.DataFrame           # every 2025-26 regular-season FGA (ShotChartDetail)
    pbp_shots: pd.DataFrame       # every FGA seen in play-by-play, with minutes on floor
    assists: pd.DataFrame         # game_id, event_id, assister, shooter
    stints: pd.DataFrame          # one row per (ten-man stint, team on offense)
    player_stints: pd.DataFrame   # player_id, minutes (continuous stretches)
    pt_defend: pd.DataFrame       # player_id, category (Overall/P3/P2/R), A, M, E
    pt_shot_cells: pd.DataFrame   # player_id, general_range, def_dist, FG3M, FG3A
    combine: pd.DataFrame         # index player_id: wingspan + drill tests (most recent)
    game_logs: pd.DataFrame       # 2025-26 player-game box rows
    durability: pd.DataFrame      # index player_id: roster_games, games_missed (3 seasons)
    team_usage: pd.DataFrame
    names: dict
    games: pd.DataFrame
    team_season_stats: pd.DataFrame
    team_pace: pd.Series          # team_id -> possessions per 48 minutes
    league_counts: dict           # league-wide totals: shooting fouls, FT points, blocks by category
    pbp_events_total: int
    pbp_events_unresolved: int
    pbp_diagnostics: dict
    pbp_examples: list
    turnover_types: pd.DataFrame  # distinct turnover types seen, with counts and class
    checks: list = field(default_factory=list)   # data checks the docs ask for (doc 02 checklist)


def _sum_by_player(df, id_col, cols):
    if df.empty:
        return pd.DataFrame(columns=cols, dtype=float)
    d = df[[id_col] + cols].copy()
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    out = d.groupby(d[id_col].astype(int))[cols].sum(min_count=1)
    out.index.name = "player_id"
    return out.astype(float)


def _col(df, id_col, src, dst):
    return _sum_by_player(df, id_col, [src]).rename(columns={src: dst})


def height_inches(text):
    """'6-8' -> 80.0"""
    if text is None or (isinstance(text, float) and np.isnan(text)) or "-" not in str(text):
        return np.nan
    feet, inches = str(text).split("-")
    return int(feet) * 12 + float(inches)


def minutes_value(text):
    """Box-score minutes ('34:12', 'PT34M12.00S', 34.2, None) -> float minutes."""
    if text is None or (isinstance(text, float) and np.isnan(text)) or text == "":
        return 0.0
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text)
    if s.startswith("PT"):
        m, sec = s[2:].rstrip("S").split("M")
        return int(m) + float(sec) / 60
    if ":" in s:
        m, sec = s.split(":")
        return int(m) + float(sec) / 60
    return float(s)


def load_teams():
    from nba_api.stats.static import teams as static_teams
    rows = [t for t in static_teams.get_teams() if t["id"] in plan.TEAM_IDS]
    return pd.DataFrame({
        "team_id": [t["id"] for t in rows],
        "abbreviation": [t["abbreviation"] for t in rows],
        "city": [t["city"] for t in rows],
        "name": [t["nickname"] for t in rows],
    })


def load_roster(loader):
    frames = []
    for t in plan.TEAM_IDS:
        df = loader.frame(f"roster_{t}")
        frames.append(df.assign(team_id=t))
    r = pd.concat(frames, ignore_index=True)
    dup = r[r.duplicated("PLAYER_ID", keep=False)]
    if not dup.empty:
        raise ValueError(f"players on more than one final roster: {dup[['PLAYER_ID', 'team_id']].values.tolist()}")
    height = r["HEIGHT"].map(height_inches)
    weight = pd.to_numeric(r["WEIGHT"], errors="coerce")
    # A few roster rows have no listed height/weight; stats.nba.com's player index
    # publishes the same listed measurements.
    try:
        idx = loader.frame("player_index").set_index("PERSON_ID")
        pid = r["PLAYER_ID"].astype(int)
        height = height.fillna(pid.map(idx["HEIGHT"].map(height_inches)))
        weight = weight.fillna(pid.map(pd.to_numeric(idx["WEIGHT"], errors="coerce")))
    except KeyError:
        pass
    position = r["POSITION"].fillna("").astype(str).str.strip()
    unknown = sorted(set(position) - set(POSITION_INDEX))
    if unknown:
        bad = r.loc[position.isin(unknown), ["PLAYER_ID", "PLAYER", "POSITION"]].values.tolist()
        raise ValueError(f"published position labels outside the seven in doc 11: {bad}")
    return pd.DataFrame({
        "player_id": r["PLAYER_ID"].astype(int),
        "team_id": r["team_id"].astype(int),
        "display_name": r["PLAYER"].astype(str),
        "jersey": r["NUM"].astype(str),
        "position": position,
        "position_index": position.map(POSITION_INDEX).astype(int),
        "birth_date": r["BIRTH_DATE"].astype(str),
        "experience": r["EXP"].astype(str),
        "age": pd.to_numeric(r["AGE"], errors="coerce"),
        "height_in": height.to_numpy(),
        "weight_lb": weight.to_numpy(),
    })


# --------------------------------------------------------------------------- #
# Play-by-play
# --------------------------------------------------------------------------- #

def _game_pbp(loader, gid, box, stints):
    """liveData when cached (primary, doc 11), otherwise PlayByPlayV3."""
    try:
        actions = loader.game_frame("live_pbp", gid, "Actions")
    except KeyError:
        return account_v3(gid, loader.game_frame("pbp", gid, "PlayByPlay"), box, stints), "v3"
    return account_live(gid, actions, box, stints), "live"


def load_box_and_pbp(loader, game_ids):
    usage = defaultdict(lambda: [0, 0, 0.0])   # (pid, tid) -> gp, gs, minutes
    names = {}
    on_court = defaultdict(lambda: defaultdict(float))
    player_events = defaultdict(lambda: defaultdict(float))
    tov_types = defaultdict(int)
    shots, assists, stint_rows, player_stints = [], [], [], []
    league = defaultdict(float)
    total = unresolved = 0
    diag = defaultdict(float)
    examples = []
    for gid in game_ids:
        box = loader.game_frame("box", gid, "PlayerStats")
        box_minutes = {}
        for row in box.itertuples(index=False):
            pid, tid = int(row.personId), int(row.teamId)
            names[pid] = (str(row.firstName), str(row.familyName))
            mins = minutes_value(row.minutes)
            if mins > 0:
                box_minutes[pid] = mins
                u = usage[(pid, tid)]
                u[0] += 1
                u[1] += 1 if str(row.position or "").strip() else 0
                u[2] += mins
        try:
            stints = stints_from_rotation(loader.game_frames("rotation", gid))
            diag["games_with_rotation"] += 1
        except KeyError:   # gamerotation is optional; most games don't have it
            stints = None
        acc, source = _game_pbp(loader, gid, box, stints)
        diag[f"games_pbp_{source}"] += 1
        for key, fields in acc.on_court.items():
            for f, v in fields.items():
                on_court[key][f] += v
        for pid, fields in acc.player_events.items():
            for f, v in fields.items():
                player_events[pid][f] += v
        for pid, types in acc.turnovers_by_type.items():
            for sub, n in types.items():
                tov_types[sub] += n
        for (event_id, shooter, team, value, made, dist, _stint, minutes_on) in acc.shots:
            shots.append((gid, event_id, shooter, team, value, made, dist, minutes_on))
        for (assister, shooter, event_id) in acc.assists:
            assists.append((gid, event_id, assister, shooter))
        for s in acc.stints:
            teams = list(s["lineups"])
            for off in teams:
                de = [t for t in teams if t != off][0]
                c = s["counts"][off]
                stint_rows.append((gid, off, s["lineups"][off], s["lineups"][de],
                                   stint_possessions(c), c.get("pts", 0.0),
                                   tuple(c.get("shot_ids", ()))))
        player_stints.extend(acc.player_stints)
        league["shooting_fouls"] += acc.shooting_fouls
        league["shooting_foul_ft_points"] += acc.shooting_foul_ft_points
        total += acc.events_total
        unresolved += acc.events_unresolved
        for k, v in acc.diagnostics.items():
            diag[k] += v
        examples.extend(acc.examples)
        # Reconstructed minutes vs official box-score minutes, per player-game.
        for pid, mins in box_minutes.items():
            err = abs(acc.seconds_on.get(pid, 0.0) / 60 - mins)
            diag["player_games"] += 1
            diag["minutes_abs_error_sum"] += err
            diag["player_games_off_by_over_1_min"] += err > 1.0

    team_usage = pd.DataFrame(
        [(p, t, gp, gs, m) for (p, t), (gp, gs, m) in usage.items()],
        columns=["player_id", "team_id", "games_played", "games_started", "minutes"])
    oc = pd.DataFrame([{"player_id": p, **fields} for (p, _t), fields in on_court.items()])
    if oc.empty:
        oc = pd.DataFrame(columns=["player_id", *ON_COURT_FIELDS])
    oc = oc.groupby("player_id").sum().reindex(columns=list(ON_COURT_FIELDS), fill_value=0.0)
    pe = pd.DataFrame.from_dict({p: dict(f) for p, f in player_events.items()}, orient="index")
    pe = pe.reindex(columns=list(PLAYER_EVENT_FIELDS)).fillna(0.0)
    pe.index.name = "player_id"
    from .pbp import turnover_class
    tov = pd.DataFrame([(k, n, turnover_class(k)) for k, n in sorted(tov_types.items())],
                       columns=["type", "count", "class"])
    return dict(
        team_usage=team_usage, names=names, on_court=oc.astype(float), player_events=pe,
        turnover_types=tov,
        pbp_shots=pd.DataFrame(shots, columns=["game_id", "event_id", "shooter", "team_id", "value",
                                               "made", "distance", "minutes_on"]),
        assists=pd.DataFrame(assists, columns=["game_id", "event_id", "assister", "shooter"]),
        stints=pd.DataFrame(stint_rows, columns=["game_id", "offense_team", "offense", "defense",
                                                 "poss", "pts", "shot_ids"]),
        player_stints=pd.DataFrame(player_stints, columns=["player_id", "minutes"]),
        league=dict(league), total=total, unresolved=unresolved, diag=dict(diag),
        examples=examples)


def box_home_away(loader, game_id):
    """(home_team_id, away_team_id) as stated by the game's box score."""
    req = next(r for r in plan.game_requests(game_id) if r.endpoint == "boxscoretraditionalv3")
    bs = loader.store.get(req.endpoint, req.params)["boxScoreTraditional"]
    return int(bs["homeTeam"]["teamId"]), int(bs["awayTeam"]["teamId"])


def load_games(loader):
    """One row per game: two team rows from the game log (date, points), home/away from
    the box score (the game log's 'vs.'/'@' text is not reliable for neutral-site games)."""
    df = loader.frame(f"team_game_log_{SEASON}")
    rows, problems = [], []
    for gid, g in df.groupby(df["GAME_ID"].astype(str)):
        pts = {int(t): p for t, p in zip(g["TEAM_ID"], g["PTS"])}
        if len(g) != 2 or len(pts) != 2:
            problems.append(f"{gid}: {len(g)} rows {g['MATCHUP'].tolist()}")
            continue
        try:
            home, away = box_home_away(loader, gid)
        except KeyError:
            problems.append(f"{gid}: box score not downloaded")
            continue
        if {home, away} != set(pts):
            problems.append(f"{gid}: box score teams {home}/{away} vs game log {sorted(pts)}")
            continue
        rows.append((gid, str(g["GAME_DATE"].iloc[0]), home, away,
                     None if pd.isna(pts[home]) else int(pts[home]),
                     None if pd.isna(pts[away]) else int(pts[away])))
    if problems:
        raise ValueError("team game log: cannot build these games:\n  " + "\n  ".join(problems[:20]))
    return pd.DataFrame(rows, columns=["game_id", "game_date", "home_team_id", "away_team_id",
                                       "home_points", "away_points"]) \
        .sort_values(["game_date", "game_id"]).reset_index(drop=True)


def load_team_season_stats(loader):
    rows = []
    for name in ("team_base_totals", "team_advanced_totals"):
        df = loader.frame(name)
        num = [c for c in df.columns if c not in ("TEAM_ID", "TEAM_NAME", "CFID", "CFPARAMS")
               and not c.endswith("_RANK") and pd.api.types.is_numeric_dtype(df[c])]
        for row in df.itertuples(index=False):
            for c in num:
                rows.append((int(getattr(row, "TEAM_ID")), f"{name.split('_')[1]}.{c}",
                             float(getattr(row, c))))
    return pd.DataFrame(rows, columns=["team_id", "stat", "value"]).drop_duplicates(["team_id", "stat"])


def load_team_pace(loader):
    df = loader.frame("team_advanced_totals")
    return pd.Series(pd.to_numeric(df["PACE"]).to_numpy(), index=df["TEAM_ID"].astype(int))


# --------------------------------------------------------------------------- #
# Combine, game logs, durability
# --------------------------------------------------------------------------- #

COMBINE_TESTS = ("THREE_QUARTER_SPRINT", "LANE_AGILITY_TIME", "MODIFIED_LANE_AGILITY_TIME",
                 "MAX_VERTICAL_LEAP", "STANDING_VERTICAL_LEAP", "BENCH_PRESS")


def _latest(frames, cols):
    if not frames:
        return pd.DataFrame(columns=cols)
    c = pd.concat(frames, ignore_index=True)
    c = c[pd.to_numeric(c["PLAYER_ID"], errors="coerce") > 0]
    out = {}
    for col in cols:
        v = c[["PLAYER_ID", "year", col]].copy()
        v[col] = pd.to_numeric(v[col], errors="coerce")
        v = v.dropna(subset=[col]).sort_values("year").groupby(v["PLAYER_ID"].astype(int)).tail(1)
        out[col] = pd.Series(v[col].to_numpy(), index=v["PLAYER_ID"].astype(int).to_numpy())
    df = pd.DataFrame(out)
    df.index.name = "player_id"
    return df


def load_combine(loader):
    """Most recent combine measurement per player and per test (a player re-measured in
    a later year keeps the later value)."""
    anthro, drills = [], []
    for year in range(plan.COMBINE_FIRST_YEAR, plan.COMBINE_LAST_YEAR + 1):
        a = loader.frame(f"combine_anthro_{year}")
        if not a.empty:
            anthro.append(a.assign(year=year))
        d = loader.frame(f"combine_drills_{year}")
        if not d.empty:
            drills.append(d.assign(year=year))
    w = _latest(anthro, ["WINGSPAN"]).rename(columns={"WINGSPAN": "wingspan_in"})
    t = _latest(drills, list(COMBINE_TESTS))
    return w.join(t, how="outer")


def load_game_logs(loader):
    df = loader.frame(f"player_game_logs_{SEASON}")
    out = pd.DataFrame({"player_id": df["PLAYER_ID"].astype(int),
                        "game_id": df["GAME_ID"].astype(str),
                        "game_date": df["GAME_DATE"].astype(str),
                        "MIN": df["MIN"].map(minutes_value)})
    for c in ("PTS", "FGM", "FGA", "FTM", "FTA", "OREB", "DREB", "STL", "AST", "BLK", "PF", "TOV"):
        out[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return out


def season_game_ids(loader, season):
    df = loader.frame(f"team_game_log_{season}")
    return sorted(df["GAME_ID"].astype(str).unique())


def load_durability(loader):
    """Doc 04: roster games = team games where he is in the box score (DNP rows included)
    or on the inactive list; games missed = inactive, or a DNP comment other than
    Coach's Decision. Regular season, trailing three seasons."""
    roster_games, missed = defaultdict(int), defaultdict(int)
    comments = defaultdict(int)
    for season in DURABILITY_SEASONS:
        for gid in season_game_ids(loader, season):
            reqs = plan.durability_game_requests(gid)
            box = loader.frame(reqs[0].name, "PlayerStats", request=reqs[0])
            inactive = loader.frame(reqs[1].name, "InactivePlayers", request=reqs[1])
            seen, out = set(), set()
            for row in box.itertuples(index=False):
                key = (int(row.personId), int(row.teamId))
                seen.add(key)
                comment = str(row.comment or "").strip()
                if minutes_value(row.minutes) == 0 and comment:
                    comments[comment] += 1
                    if "coach's decision" not in comment.lower() and \
                            "coach’s decision" not in comment.lower():
                        out.add(key)
            for row in inactive.itertuples(index=False):
                key = (int(row.personId), int(row.teamId))
                seen.add(key)
                out.add(key)
            for pid, _t in seen:
                roster_games[pid] += 1
            for pid, _t in out:
                missed[pid] += 1
    df = pd.DataFrame({"roster_games": pd.Series(roster_games, dtype=float),
                       "games_missed": pd.Series(missed, dtype=float)}).fillna(0.0)
    df.index.name = "player_id"
    return df, dict(comments)


# --------------------------------------------------------------------------- #
# Season dashboards
# --------------------------------------------------------------------------- #

# LeagueDashPtDefend publishes each category with its own column names.
PT_DEFEND_COLUMNS = {
    "Overall": [("D_FGM", "D_FGA", "NORMAL_FG_PCT")],
    "3 Pointers": [("FG3M", "FG3A", "NS_FG3_PCT"), ("D_FGM", "D_FGA", "NORMAL_FG_PCT")],
    "2 Pointers": [("FG2M", "FG2A", "NS_FG2_PCT"), ("D_FGM", "D_FGA", "NORMAL_FG_PCT")],
    "Less Than 6Ft": [("FGM_LT_06", "FGA_LT_06", "NS_LT_06_PCT"),
                      ("D_FGM", "D_FGA", "NORMAL_FG_PCT")],
}


def load_pt_defend(loader):
    """Doc 02 contest accounting: Overall, P3 = '3 Pointers', R = 'Less Than 6Ft',
    P2 = '2 Pointers' minus 'Less Than 6Ft' (A, M and E each subtracted). E = q * A."""
    cats = {}
    for cat, options in PT_DEFEND_COLUMNS.items():
        df = loader.frame(plan.pt_defend_name(cat))
        cols = next((o for o in options if all(c in df.columns for c in o)), None)
        if cols is None:
            raise ValueError(f"pt_defend|{cat}: none of the expected column sets {options} in "
                             f"{list(df.columns)}")
        m_col, a_col, q_col = cols
        d = pd.DataFrame({"player_id": df["CLOSE_DEF_PERSON_ID"].astype(int),
                          "M": pd.to_numeric(df[m_col], errors="coerce").fillna(0.0),
                          "A": pd.to_numeric(df[a_col], errors="coerce").fillna(0.0),
                          "q": pd.to_numeric(df[q_col], errors="coerce")})
        d["E"] = d["q"].fillna(0.0) * d["A"]
        d = d.groupby("player_id")[["A", "M", "E"]].sum()
        cats[cat] = d
    ids = sorted(set().union(*[set(d.index) for d in cats.values()]))
    out = []
    for name, d in (("Overall", cats["Overall"]), ("P3", cats["3 Pointers"]),
                    ("R", cats["Less Than 6Ft"])):
        out.append(d.reindex(ids, fill_value=0.0).assign(category=name))
    p2 = cats["2 Pointers"].reindex(ids, fill_value=0.0) - cats["Less Than 6Ft"].reindex(ids, fill_value=0.0)
    out.append(p2.assign(category="P2"))
    res = pd.concat(out).reset_index().rename(columns={"index": "player_id"})
    return res, cats


def pt_defend_checks(cats, league_fga):
    """The doc 02 checklist assertions on LeagueDashPtDefend, as (name, ok, detail)."""
    o, p3, p2, r = (cats[k] for k in ("Overall", "3 Pointers", "2 Pointers", "Less Than 6Ft"))
    ids = o.index
    split = p3["A"].reindex(ids, fill_value=0).sum() + p2["A"].reindex(ids, fill_value=0).sum()
    checks = [
        ("ptdefend: 3 Pointers + 2 Pointers D_FGA within 1% of Overall",
         abs(split - o["A"].sum()) <= 0.01 * o["A"].sum(), f"{split:.0f} vs {o['A'].sum():.0f}"),
    ]
    lt6 = r["A"].reindex(p2.index, fill_value=0)
    bad = p2.index[p2["A"] + 1e-9 < lt6].tolist()
    checks.append(("ptdefend: 2 Pointers D_FGA >= Less Than 6Ft D_FGA for every player",
                   not bad, f"violations: {bad[:10]}"))
    checks.append(("ptdefend: league D_FGA within 1% of league FGA",
                   abs(o["A"].sum() - league_fga) <= 0.01 * league_fga,
                   f"{o['A'].sum():.0f} vs {league_fga:.0f}"))
    return checks


def load_pt_shot_cells(loader):
    """Doc 02 E2: GeneralRange {Catch and Shoot, Pullups} x the four closest-defender buckets."""
    rows = []
    for g in ("Catch and Shoot", "Pullups"):
        for d in plan.CLOSE_DEF_DIST_RANGES[1:]:
            df = loader.frame(plan.pt_shot_name(g, d, ""))
            s = _sum_by_player(df, "PLAYER_ID", ["FG3M", "FG3A"])
            rows.append(s.assign(general_range=g, def_dist=d).reset_index())
    return pd.concat(rows, ignore_index=True)


HUSTLE_COLUMNS = ("CONTESTED_SHOTS", "DEFLECTIONS", "CHARGES_DRAWN", "SCREEN_ASSISTS",
                  "SCREEN_AST_PTS", "OFF_LOOSE_BALLS_RECOVERED", "DEF_LOOSE_BALLS_RECOVERED",
                  "LOOSE_BALLS_RECOVERED", "OFF_BOXOUTS", "DEF_BOXOUTS")
PASSING_COLUMNS = ("PASSES_MADE", "POTENTIAL_AST", "AST_ADJ", "FT_AST", "SECONDARY_AST",
                   "AST_POINTS_CREATED")
REBOUNDING_COLUMNS = ("OREB_CHANCES", "DREB_CHANCES", "OREB_CHANCE_DEFER", "DREB_CHANCE_DEFER")
SYNERGY_OFFENSE_USED = ("Isolation", "PRBallHandler", "Postup", "Cut", "OffScreen", "Handoff",
                        "Transition")


def load_inputs(loader, oc, pe):
    base = loader.frame("player_base_totals")
    inputs = _sum_by_player(base, "PLAYER_ID", ["GP", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM",
                                                "FTA", "OREB", "DREB", "AST", "TOV", "STL", "BLK",
                                                "PF", "PTS"])

    def add(df):
        nonlocal inputs
        inputs = inputs.join(df, how="outer")

    late = [loader.frame(plan.shot_clock_name(r)) for r in ("7-4 Late", "4-0 Very Late")]
    add(_col(pd.concat(late), "PLAYER_ID", "FGA", "LATE_CLOCK_FGA"))
    add(_col(loader.frame(plan.pt_shot_name("Catch and Shoot", "", "")), "PLAYER_ID", "FGA", "CS_FGA"))
    add(_col(loader.frame(plan.pt_shot_name("Pullups", "", "")), "PLAYER_ID", "FGA", "PU_FGA"))

    drives = loader.frame("pt_Drives")
    add(_sum_by_player(drives, "PLAYER_ID", ["DRIVES", "DRIVE_FGA", "DRIVE_PASSES", "DRIVE_FTA"]))
    add(_sum_by_player(loader.frame("pt_Passing"), "PLAYER_ID", list(PASSING_COLUMNS)))
    poss = loader.frame("pt_Possessions").copy()
    poss["DRIBBLES"] = pd.to_numeric(poss["TOUCHES"]) * pd.to_numeric(poss["AVG_DRIB_PER_TOUCH"])
    add(_sum_by_player(poss, "PLAYER_ID", ["TOUCHES", "DRIBBLES"]))
    reb = loader.frame("pt_Rebounding")
    add(_sum_by_player(reb, "PLAYER_ID", ["OREB", "DREB"] + list(REBOUNDING_COLUMNS))
        .rename(columns={"OREB": "TRK_OREB", "DREB": "TRK_DREB"}))
    sd = loader.frame("pt_SpeedDistance").copy()
    for c in ("MIN", "AVG_SPEED_OFF", "AVG_SPEED_DEF", "DIST_MILES_OFF", "DIST_MILES_DEF"):
        sd[c] = pd.to_numeric(sd[c], errors="coerce")
    sd["SPEED_OFF_X_MIN"] = sd["AVG_SPEED_OFF"] * sd["MIN"]
    sd["SPEED_DEF_X_MIN"] = sd["AVG_SPEED_DEF"] * sd["MIN"]
    s = _sum_by_player(sd, "PLAYER_ID", ["MIN", "SPEED_OFF_X_MIN", "SPEED_DEF_X_MIN",
                                         "DIST_MILES_OFF", "DIST_MILES_DEF"])
    s["AVG_SPEED_OFF"] = s["SPEED_OFF_X_MIN"] / s["MIN"]   # minutes-weighted across team rows
    s["AVG_SPEED_DEF"] = s["SPEED_DEF_X_MIN"] / s["MIN"]
    add(s[["MIN", "AVG_SPEED_OFF", "AVG_SPEED_DEF", "DIST_MILES_OFF", "DIST_MILES_DEF"]]
        .rename(columns={"MIN": "SPEED_MIN"}))

    add(_sum_by_player(loader.frame("player_hustle"), "PLAYER_ID", list(HUSTLE_COLUMNS)))

    total_poss = None
    for pt in plan.PLAY_TYPES:
        df = loader.frame(plan.play_type_name("offensive", pt))
        both = _sum_by_player(df, "PLAYER_ID", ["POSS", "PTS"])
        add(both.rename(columns={"POSS": f"SYN_{pt}_POSS", "PTS": f"SYN_{pt}_PTS"}))
        s_ = both["POSS"]
        total_poss = s_ if total_poss is None else total_poss.add(s_, fill_value=0)
    add(total_poss.rename("SYN_TOTAL_POSS").to_frame())
    post_d = loader.frame(plan.play_type_name("defensive", "Postup"))
    add(_sum_by_player(post_d, "PLAYER_ID", ["POSS", "PTS"])
        .rename(columns={"POSS": "SYN_D_Postup_POSS", "PTS": "SYN_D_Postup_PTS"}))

    clutch = loader.frame("player_clutch_base")
    add(_sum_by_player(clutch, "PLAYER_ID", ["PTS", "FGA", "FTA"])
        .rename(columns={"PTS": "CLUTCH_PTS", "FGA": "CLUTCH_FGA", "FTA": "CLUTCH_FTA"}))

    add(oc)
    add(pe)
    inputs = inputs.fillna(0.0)
    inputs["OFF_POSS"] = possessions(inputs, "off")
    inputs["DEF_POSS"] = possessions(inputs, "def")
    return inputs


SHOT_COLUMNS = ["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "PERIOD", "MINUTES_REMAINING",
                "SECONDS_REMAINING", "ACTION_TYPE", "SHOT_TYPE", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA",
                "SHOT_DISTANCE", "LOC_X", "LOC_Y", "SHOT_MADE_FLAG", "GAME_DATE"]


def load_shots(loader):
    shots = pd.concat([loader.frame(f"shot_chart_{t}") for t in plan.TEAM_IDS], ignore_index=True)
    shots = shots[shots["SHOT_ATTEMPTED_FLAG"] == 1]
    shots = shots.drop_duplicates(["GAME_ID", "GAME_EVENT_ID"]).reset_index(drop=True)
    out = shots[SHOT_COLUMNS].copy()
    out["GAME_ID"] = out["GAME_ID"].astype(str)
    for c in ("GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "PERIOD", "MINUTES_REMAINING",
              "SECONDS_REMAINING", "SHOT_MADE_FLAG"):
        out[c] = pd.to_numeric(out[c]).astype(int)
    for c in ("SHOT_DISTANCE", "LOC_X", "LOC_Y"):
        out[c] = pd.to_numeric(out[c]).astype(float)
    return out


def assemble(loader):
    games = load_games(loader)
    pbp = load_box_and_pbp(loader, games["game_id"])
    inputs = load_inputs(loader, pbp["on_court"], pbp["player_events"])
    shots = load_shots(loader)
    pt_defend, defend_cats = load_pt_defend(loader)
    durability, dnp_comments = load_durability(loader)

    # league blocks per contest category, from play-by-play (doc 02 E5)
    league = dict(pbp["league"])
    for cat in ("R", "P2", "P3"):
        league[f"pbp_blocks_{cat}"] = float(inputs[f"pbp_blocks_{cat}"].sum())

    checks = pt_defend_checks(defend_cats, float(inputs["FGA"].sum()))
    ps = pbp["pbp_shots"]
    joined = ps.merge(shots[["GAME_ID", "GAME_EVENT_ID"]], left_on=["game_id", "event_id"],
                      right_on=["GAME_ID", "GAME_EVENT_ID"], how="left", indicator=True)
    matched = (joined["_merge"] == "both").mean() if len(joined) else 1.0
    checks.append(("play-by-play FGA joined to ShotChartDetail by game + event id",
                   matched >= 0.99, f"{matched:.2%} matched"))
    checks.append(("box-score DNP comments seen (Durability)", bool(dnp_comments),
                   "; ".join(f"{k}: {v}" for k, v in sorted(dnp_comments.items(),
                                                            key=lambda kv: -kv[1])[:12])))

    return League(
        teams=load_teams(),
        roster=load_roster(loader),
        inputs=inputs,
        shots=shots,
        pbp_shots=ps,
        assists=pbp["assists"],
        stints=pbp["stints"],
        player_stints=pbp["player_stints"],
        pt_defend=pt_defend,
        pt_shot_cells=load_pt_shot_cells(loader),
        combine=load_combine(loader),
        game_logs=load_game_logs(loader),
        durability=durability,
        team_usage=pbp["team_usage"],
        names=pbp["names"],
        games=games,
        team_season_stats=load_team_season_stats(loader),
        team_pace=load_team_pace(loader),
        league_counts=league,
        pbp_events_total=pbp["total"],
        pbp_events_unresolved=pbp["unresolved"],
        pbp_diagnostics=pbp["diag"],
        pbp_examples=pbp["examples"],
        turnover_types=pbp["turnover_types"],
        checks=checks,
    )
