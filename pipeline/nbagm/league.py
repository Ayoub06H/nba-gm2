"""Assemble raw cached responses into per-player input tables.

Everything here is bookkeeping: selecting real columns, summing rows that the
API splits by team, and counting on-court events. No formula from docs 02-04
lives in this module; those are in derive.py.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import plan
from .config import SEASON
from .pbp import ON_COURT_FIELDS, account_game, possessions, stints_from_rotation


@dataclass
class League:
    teams: pd.DataFrame          # team_id, abbreviation, city, name
    roster: pd.DataFrame         # one row per rostered player
    inputs: pd.DataFrame         # index player_id: every real count the derivations read
    shots: pd.DataFrame          # every 2025-26 regular-season FGA from the shot chart
    team_usage: pd.DataFrame     # (player_id, team_id): games_played, games_started, minutes
    combine: pd.DataFrame        # player_id -> wingspan (most recent combine measurement)
    names: dict                  # player_id -> (first, last) from box scores
    games: pd.DataFrame
    team_season_stats: pd.DataFrame
    pbp_events_total: int
    pbp_events_unresolved: int


def _sum_by_player(df, id_col, cols):
    if df.empty:
        return pd.DataFrame(columns=cols, dtype=float)
    out = df.groupby(df[id_col].astype(int))[cols].sum(min_count=1)
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
    names = r["PLAYER"].astype(str)
    return pd.DataFrame({
        "player_id": r["PLAYER_ID"].astype(int),
        "team_id": r["team_id"].astype(int),
        "display_name": names,
        "jersey": r["NUM"].astype(str),
        "listed_position": r["POSITION"].astype(str),
        "birth_date": r["BIRTH_DATE"].astype(str),
        "experience": r["EXP"].astype(str),
        "height_in": r["HEIGHT"].map(height_inches),
        "weight_lb": pd.to_numeric(r["WEIGHT"], errors="coerce"),
    })


def load_box_and_pbp(loader, game_ids):
    usage = defaultdict(lambda: [0, 0, 0.0])   # (pid, tid) -> gp, gs, minutes
    names = {}
    on_court = defaultdict(lambda: defaultdict(float))
    tov_types = defaultdict(lambda: defaultdict(int))
    total = unresolved = 0
    for gid in game_ids:
        box = loader.game_frame("box", gid, "PlayerStats")
        box_ids = set()
        for row in box.itertuples(index=False):
            pid, tid = int(row.personId), int(row.teamId)
            names[pid] = (str(row.firstName), str(row.familyName))
            mins = minutes_value(row.minutes)
            if mins > 0:
                box_ids.add(pid)
                u = usage[(pid, tid)]
                u[0] += 1
                u[1] += 1 if str(row.position or "").strip() else 0
                u[2] += mins
        pbp = loader.game_frame("pbp", gid, "PlayByPlay")
        stints = stints_from_rotation(loader.game_frames("rotation", gid))
        acc = account_game(gid, pbp, stints, box_ids)
        for key, fields in acc.on_court.items():
            for f, v in fields.items():
                on_court[key][f] += v
        for pid, types in acc.turnovers_by_type.items():
            for sub, n in types.items():
                tov_types[pid][sub] += n
        total += acc.events_total
        unresolved += acc.events_unresolved

    team_usage = pd.DataFrame(
        [(p, t, gp, gs, m) for (p, t), (gp, gs, m) in usage.items()],
        columns=["player_id", "team_id", "games_played", "games_started", "minutes"])
    oc = pd.DataFrame([{"player_id": p, **fields} for (p, _t), fields in on_court.items()])
    if oc.empty:
        oc = pd.DataFrame(columns=["player_id", *ON_COURT_FIELDS])
    oc = oc.groupby("player_id").sum().reindex(columns=list(ON_COURT_FIELDS), fill_value=0.0)
    tov = pd.DataFrame(
        [(p, sub, n) for p, d in tov_types.items() for sub, n in d.items()],
        columns=["player_id", "sub_type", "n"])
    return team_usage, names, oc.astype(float), tov, total, unresolved


def load_games(loader):
    df = loader.frame(f"team_game_log_{SEASON}")
    home = df[df["MATCHUP"].str.contains(" vs. ", regex=False)]
    away = df[df["MATCHUP"].str.contains(" @ ", regex=False)]
    g = home.merge(away, on="GAME_ID", suffixes=("_h", "_a"))
    if len(g) != df["GAME_ID"].nunique():
        raise ValueError("team game log: could not pair every game into home/away rows")
    return pd.DataFrame({
        "game_id": g["GAME_ID"].astype(str),
        "game_date": g["GAME_DATE_h"].astype(str),
        "home_team_id": g["TEAM_ID_h"].astype(int),
        "away_team_id": g["TEAM_ID_a"].astype(int),
        "home_points": g["PTS_h"].astype(int),
        "away_points": g["PTS_a"].astype(int),
    }).sort_values(["game_date", "game_id"]).reset_index(drop=True)


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


def load_combine(loader):
    frames = []
    for year in range(plan.COMBINE_FIRST_YEAR, plan.COMBINE_LAST_YEAR + 1):
        df = loader.frame(f"combine_anthro_{year}")
        if not df.empty:
            frames.append(df[["PLAYER_ID", "WINGSPAN"]].assign(year=year))
    c = pd.concat(frames, ignore_index=True)
    c = c[(pd.to_numeric(c["PLAYER_ID"], errors="coerce") > 0)
          & pd.to_numeric(c["WINGSPAN"], errors="coerce").notna()]
    c = c.sort_values("year").groupby(c["PLAYER_ID"].astype(int)).tail(1)
    return pd.DataFrame({"player_id": c["PLAYER_ID"].astype(int),
                         "wingspan_in": c["WINGSPAN"].astype(float)}).set_index("player_id")


def load_inputs(loader, oc, tov_types):
    base = loader.frame("player_base_totals")
    ids = base["PLAYER_ID"].astype(int)
    inputs = pd.DataFrame(index=pd.Index(ids.unique(), name="player_id"))

    def add(df):
        nonlocal inputs
        inputs = inputs.join(df, how="outer")

    add(_sum_by_player(base, "PLAYER_ID", ["GP", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM",
                                           "FTA", "OREB", "DREB", "AST", "TOV", "STL", "BLK",
                                           "PF", "PTS"]))
    loc = loader.frame("player_shot_locations")
    add(_col(loc, "PLAYER_ID", "Restricted Area|FGA", "RIM_FGA"))
    add(_col(loc, "PLAYER_ID", "Mid-Range|FGA", "MID_FGA"))

    late = [loader.frame(plan.shot_clock_name(r)) for r in ("7-4 Late", "4-0 Very Late")]
    add(_col(pd.concat(late), "PLAYER_ID", "FGA", "LATE_CLOCK_FGA"))

    add(_col(loader.frame("pt_CatchShoot"), "PLAYER_ID", "CATCH_SHOOT_FGA", "CS_FGA"))
    add(_col(loader.frame("pt_PullUpShot"), "PLAYER_ID", "PULL_UP_FGA", "PU_FGA"))
    drives = loader.frame("pt_Drives")
    add(_col(drives, "PLAYER_ID", "DRIVE_FGA", "DRIVE_FGA"))
    add(_col(drives, "PLAYER_ID", "DRIVE_PASSES", "DRIVE_PASSES"))
    passing = loader.frame("pt_Passing")
    add(_col(passing, "PLAYER_ID", "PASSES_MADE", "PASSES_MADE"))
    add(_col(passing, "PLAYER_ID", "POTENTIAL_AST", "POTENTIAL_AST"))
    add(_col(loader.frame("pt_Possessions"), "PLAYER_ID", "TOUCHES", "TOUCHES"))
    add(_col(loader.frame("pt_Rebounding"), "PLAYER_ID", "OREB_CHANCES", "OREB_CHANCES"))

    hustle = loader.frame("player_hustle")
    for src, dst in (("CONTESTED_SHOTS", "CONTESTED_SHOTS"), ("DEFLECTIONS", "DEFLECTIONS"),
                     ("CHARGES_DRAWN", "CHARGES_DRAWN"), ("SCREEN_ASSISTS", "SCREEN_ASSISTS"),
                     ("LOOSE_BALLS_RECOVERED", "LOOSE_BALLS"), ("BOX_OUTS", "BOX_OUTS")):
        add(_col(hustle, "PLAYER_ID", src, dst))

    total_poss = None
    for pt in plan.PLAY_TYPES:
        df = loader.frame(plan.play_type_name("offensive", pt))
        poss = _col(df, "PLAYER_ID", "POSS", f"SYN_{pt}_POSS")
        add(poss)
        s = poss.iloc[:, 0]
        total_poss = s if total_poss is None else total_poss.add(s, fill_value=0)
    add(total_poss.rename("SYN_TOTAL_POSS").to_frame())
    post_d = loader.frame(plan.play_type_name("defensive", "Postup"))
    add(_col(post_d, "PLAYER_ID", "POSS", "SYN_D_Postup_POSS"))
    add(_col(post_d, "PLAYER_ID", "PTS", "SYN_D_Postup_PTS"))

    matchups = pd.concat([loader.frame(f"matchups_def_{t}") for t in plan.TEAM_IDS])
    add(_sum_by_player(matchups, "DEF_PLAYER_ID", ["MATCHUP_FGA", "HELP_FGA"]))

    add(oc)
    bad_pass = tov_types[tov_types["sub_type"].str.contains("Bad Pass", case=False, regex=False)]
    add(_col(bad_pass, "player_id", "n", "BAD_PASS_TOV"))

    inputs = inputs.fillna(0.0)
    inputs["OFF_POSS"] = possessions(inputs, "off")
    inputs["DEF_POSS"] = possessions(inputs, "def")
    return inputs


def load_shots(loader):
    shots = pd.concat([loader.frame(f"shot_chart_{t}") for t in plan.TEAM_IDS], ignore_index=True)
    shots = shots[shots["SHOT_ATTEMPTED_FLAG"] == 1]
    return shots.drop_duplicates(["GAME_ID", "GAME_EVENT_ID"]).reset_index(drop=True)


def assemble(loader):
    games = load_games(loader)
    team_usage, names, oc, tov, total, unresolved = load_box_and_pbp(loader, games["game_id"])
    return League(
        teams=load_teams(),
        roster=load_roster(loader),
        inputs=load_inputs(loader, oc, tov),
        shots=load_shots(loader),
        team_usage=team_usage,
        combine=load_combine(loader),
        names=names,
        games=games,
        team_season_stats=load_team_season_stats(loader),
        pbp_events_total=total,
        pbp_events_unresolved=unresolved,
    )
