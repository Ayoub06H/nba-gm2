"""Turn raw cached stats.nba.com payloads into pandas DataFrames.

Every column the build reads is checked against REQUIRED_COLUMNS first, so a
renamed or missing upstream column fails loudly with the endpoint and column
named, instead of silently producing a wrong value.
"""

import pandas as pd

from . import plan

V3_ENDPOINTS = {"playbyplayv3", "boxscoretraditionalv3", "boxscoresummaryv3"}


class SchemaError(RuntimeError):
    pass


def tables(endpoint, payload):
    """All result sets in a payload, as {name: DataFrame}."""
    if endpoint == "live.playbyplay":
        return {"Actions": pd.DataFrame(payload["game"]["actions"])}
    if endpoint in V3_ENDPOINTS:
        from nba_api.stats.endpoints._parsers import get_parser_for_endpoint
        data_sets = get_parser_for_endpoint(endpoint, payload).get_data_sets()
        return {name: pd.DataFrame(ds["data"], columns=list(ds["headers"]))
                for name, ds in data_sets.items()}
    if endpoint == "leaguedashplayershotlocations":
        return {"ShotLocations": _shot_locations(payload)}
    results = payload.get("resultSets", payload.get("resultSet"))
    if results is None:
        raise SchemaError(f"{endpoint}: payload has no resultSets")
    if isinstance(results, dict):
        results = [results]
    return {r["name"]: pd.DataFrame(r["rowSet"], columns=r["headers"]) for r in results}


def _shot_locations(payload):
    """Flatten the two-level header (zone x FGM/FGA/FG_PCT) into 'Zone|FGM' columns."""
    rs = payload["resultSets"]
    zone_header, column_header = rs["headers"][0], rs["headers"][1]
    columns = list(column_header["columnNames"])
    skip = zone_header.get("columnsToSkip", 0)
    span = zone_header.get("columnSpan", 3)
    names = columns[:skip]
    for i, zone in enumerate(zone_header["columnNames"]):
        for c in columns[skip + i * span: skip + (i + 1) * span]:
            names.append(f"{zone}|{c}")
    return pd.DataFrame(rs["rowSet"], columns=names)


# Columns the build reads, per request name prefix / endpoint. Checked at
# gather time (smoke mode) and again before every build.
REQUIRED_COLUMNS = {
    "player_index": ("PlayerIndex", ["PERSON_ID", "HEIGHT", "WEIGHT"]),
    "player_base_totals": ("LeagueDashPlayerStats", [
        "PLAYER_ID", "TEAM_ID", "GP", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
        "OREB", "DREB", "AST", "TOV", "STL", "BLK", "PF", "PTS"]),
    "player_clutch_base": ("LeagueDashPlayerClutch", ["PLAYER_ID", "PTS", "FGA", "FTA"]),
    "player_hustle": ("HustleStatsPlayer", [
        "PLAYER_ID", "CONTESTED_SHOTS", "DEFLECTIONS", "CHARGES_DRAWN", "SCREEN_ASSISTS",
        "SCREEN_AST_PTS", "OFF_LOOSE_BALLS_RECOVERED", "DEF_LOOSE_BALLS_RECOVERED",
        "LOOSE_BALLS_RECOVERED", "OFF_BOXOUTS", "DEF_BOXOUTS"]),
    "pt_Drives": ("LeagueDashPtStats", ["PLAYER_ID", "DRIVES", "DRIVE_FGA", "DRIVE_PASSES",
                                        "DRIVE_FTA"]),
    "pt_Passing": ("LeagueDashPtStats", ["PLAYER_ID", "PASSES_MADE", "POTENTIAL_AST", "AST_ADJ",
                                         "FT_AST", "SECONDARY_AST", "AST_POINTS_CREATED"]),
    "pt_Possessions": ("LeagueDashPtStats", ["PLAYER_ID", "TOUCHES", "AVG_DRIB_PER_TOUCH"]),
    "pt_Rebounding": ("LeagueDashPtStats", ["PLAYER_ID", "OREB", "DREB", "OREB_CHANCES",
                                            "DREB_CHANCES", "OREB_CHANCE_DEFER",
                                            "DREB_CHANCE_DEFER"]),
    "pt_SpeedDistance": ("LeagueDashPtStats", ["PLAYER_ID", "MIN", "AVG_SPEED_OFF",
                                               "AVG_SPEED_DEF", "DIST_MILES_OFF",
                                               "DIST_MILES_DEF"]),
    "pt_shot": ("LeagueDashPTShots", ["PLAYER_ID", "FGA", "FG3M", "FG3A"]),
    "pt_shot_clock": ("LeagueDashPTShots", ["PLAYER_ID", "FGA"]),
    "pt_defend": (None, ["CLOSE_DEF_PERSON_ID"]),
    "synergy": ("SynergyPlayType", ["PLAYER_ID", "POSS", "PTS"]),
    "shot_chart": ("Shot_Chart_Detail", [
        "GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "PERIOD", "MINUTES_REMAINING",
        "SECONDS_REMAINING", "ACTION_TYPE", "SHOT_TYPE", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA",
        "SHOT_DISTANCE", "LOC_X", "LOC_Y", "SHOT_ATTEMPTED_FLAG", "SHOT_MADE_FLAG",
        "GAME_DATE"]),
    "roster": ("CommonTeamRoster", ["TeamID", "PLAYER_ID", "PLAYER", "NUM", "POSITION",
                                    "HEIGHT", "WEIGHT", "BIRTH_DATE", "AGE", "EXP"]),
    "team_game_log": ("LeagueGameLog", ["TEAM_ID", "GAME_ID", "GAME_DATE", "MATCHUP", "PTS"]),
    "team_advanced_totals": ("LeagueDashTeamStats", ["TEAM_ID", "PACE"]),
    "player_game_logs": ("PlayerGameLogs", [
        "PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN", "PTS", "FGM", "FGA", "FTM", "FTA", "OREB",
        "DREB", "STL", "AST", "BLK", "PF", "TOV"]),
    "combine_anthro": ("Results", ["PLAYER_ID", "WINGSPAN"]),
    "combine_drills": ("Results", ["PLAYER_ID", "THREE_QUARTER_SPRINT", "LANE_AGILITY_TIME",
                                   "MODIFIED_LANE_AGILITY_TIME", "MAX_VERTICAL_LEAP",
                                   "STANDING_VERTICAL_LEAP", "BENCH_PRESS"]),
    "live_pbp": ("Actions", ["actionNumber", "clock", "period", "teamId", "personId",
                             "actionType", "subType"]),
    "summary": ("InactivePlayers", ["personId", "teamId"]),
    "pbp": ("PlayByPlay", ["actionNumber", "clock", "period", "teamId", "personId",
                           "actionType", "subType", "description", "shotResult", "isFieldGoal"]),
    "rotation": (None, ["PERSON_ID", "TEAM_ID", "IN_TIME_REAL", "OUT_TIME_REAL"]),
    "box": ("PlayerStats", ["personId", "teamId", "firstName", "familyName", "position",
                            "comment", "minutes"]),
}


def required_spec(request_name):
    for prefix in sorted(REQUIRED_COLUMNS, key=len, reverse=True):
        if request_name == prefix or request_name.startswith(prefix + "_") \
                or request_name.startswith(prefix + "|"):
            return REQUIRED_COLUMNS[prefix]
    return None


def check_columns(request_name, endpoint, payload):
    """Raise SchemaError if a column the build depends on is missing."""
    spec = required_spec(request_name)
    if spec is None:
        return
    set_name, cols = spec
    ts = tables(endpoint, payload)
    frames = list(ts.values()) if set_name is None else [ts.get(set_name)]
    for df in frames:
        if df is None:
            raise SchemaError(f"{request_name} ({endpoint}): result set {set_name!r} missing; "
                              f"got {sorted(ts)}")
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise SchemaError(f"{request_name} ({endpoint}): missing columns {missing}; "
                              f"available: {list(df.columns)}")


class Loader:
    """Read named requests from the raw cache as DataFrames."""

    def __init__(self, store):
        self.store = store
        self._league = plan.by_name(plan.all_league_and_team_requests())

    def frame(self, name, result_set=None, request=None):
        req = request or self._league[name]
        payload = self.store.get(req.endpoint, req.params)
        check_columns(req.name, req.endpoint, payload)
        ts = tables(req.endpoint, payload)
        if result_set is None:
            spec = required_spec(req.name)
            result_set = spec[0] if spec and spec[0] else next(iter(ts))
        return ts[result_set]

    def frames(self, name, request=None):
        req = request or self._league[name]
        payload = self.store.get(req.endpoint, req.params)
        check_columns(req.name, req.endpoint, payload)
        return tables(req.endpoint, payload)

    def game_frame(self, kind, game_id, result_set=None):
        req = next(r for r in plan.game_requests(game_id) if r.name.startswith(kind + "_"))
        return self.frame(req.name, result_set=result_set, request=req)

    def game_frames(self, kind, game_id):
        req = next(r for r in plan.game_requests(game_id) if r.name.startswith(kind + "_"))
        return self.frames(req.name, request=req)
