"""A synthetic raw cache in the exact response shapes stats.nba.com returns.

Used to run the full offline build end to end without network access. The
numbers are random but internally consistent (box scores, play-by-play,
rotations and dashboards all come from the same simulated games), so every
proportion the build forms stays a valid proportion.

This is test scaffolding only. Nothing here ever reaches the real league file.
"""

from collections import defaultdict

import numpy as np

from nbagm import plan
from nbagm.config import COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR, SEASON
from nbagm.rawstore import RawStore

PLAYERS_PER_TEAM = 11          # player 11 is rostered but never plays
ZONES = ("Restricted Area", "In The Paint (Non-RA)", "Mid-Range", "Left Corner 3",
         "Right Corner 3", "Above the Break 3", "Backcourt")
TWO_PT_SHOTS = (("Driving Layup Shot", "Restricted Area"), ("Driving Dunk Shot", "Restricted Area"),
                ("Dunk Shot", "Restricted Area"), ("Cutting Layup Shot", "Restricted Area"),
                ("Floating Jump shot", "In The Paint (Non-RA)"), ("Pullup Jump shot", "Mid-Range"))
TOV_TYPES = ("Bad Pass", "Lost Ball", "Traveling", "Offensive Foul")


def rs(name, headers, rows):
    return {"resultSets": [{"name": name, "headers": list(headers), "rowSet": [list(r) for r in rows]}]}


def pid(team_index, k):
    return 1_000_000 + team_index * 20 + k


def clock(period, elapsed_tenths):
    remaining = (720 if period <= 4 else 300) * 10 - elapsed_tenths
    return f"PT{remaining // 600:02d}M{(remaining % 600) / 10:05.2f}S"


class SyntheticLeague:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
        self.teams = list(plan.TEAM_IDS)
        self.roster = {t: [pid(i, k) for k in range(1, PLAYERS_PER_TEAM + 1)]
                       for i, t in enumerate(self.teams)}
        self.team_of = {p: t for t, ps in self.roster.items() for p in ps}
        self.box = defaultdict(lambda: defaultdict(float))     # season totals per player
        self.minutes = defaultdict(float)
        self.shots = defaultdict(list)                          # team -> shot chart rows
        self.games = []

    # -- one game ------------------------------------------------------------
    def play(self, game_id, date, home, away):
        rng = self.rng
        actions, stints = [], []
        n = [0]

        def act(period, t, team, person, action_type, sub_type="", desc="", result=None, fg=0,
                shot_value=None):
            n[0] += 1
            actions.append({"actionNumber": n[0], "clock": clock(period, t), "period": period,
                            "teamId": team, "personId": person, "actionType": action_type,
                            "subType": sub_type, "description": desc, "shotResult": result,
                            "isFieldGoal": fg, "shotValue": shot_value})
            return n[0]

        def lineups(team, period, half):
            ps = self.roster[team]
            if half == 0:
                return ps[0:5]
            return [ps[0], ps[1], ps[7], ps[8], ps[9]] if period == 4 else [ps[0], ps[1], ps[2], ps[5], ps[6]]

        points = {home: 0, away: 0}
        for period in range(1, 5):
            base = (period - 1) * 7200
            for team in (home, away):
                first, second = lineups(team, period, 0), lineups(team, period, 1)
                for p in set(first) | set(second):
                    t_in = base if p in first else base + 3600
                    t_out = base + 7200 if p in second else base + 3600
                    stints.append((team, p, t_in, t_out))
                    self.minutes[p] += (t_out - t_in) / 600
            act(period, 0, None, 0, "period", "start")
            offense = home if period % 2 else away
            for i in range(48):
                t = i * 150 + 70
                half = 0 if t < 3600 else 1
                if i == 24:
                    for team in (home, away):
                        outs = set(lineups(team, period, 0)) - set(lineups(team, period, 1))
                        for p in sorted(outs):
                            act(period, 3600, team, p, "Substitution", "", "SUB")
                defense = away if offense == home else home
                off_on, def_on = lineups(offense, period, half), lineups(defense, period, half)
                self._possession(act, period, t, offense, defense, off_on, def_on, points,
                                 game_id, date)
                offense = defense
            act(period, 7200, None, 0, "period", "end")

        self._box_minutes_and_gp(game_id, home, away, stints)
        self.games.append((game_id, date, home, away, points[home], points[away]))
        pbp = {"game": {"gameId": game_id, "videoAvailable": 0, "actions": actions}}
        rot_headers = ["GAME_ID", "TEAM_ID", "TEAM_CITY", "TEAM_NAME", "PERSON_ID", "PLAYER_FIRST",
                       "PLAYER_LAST", "IN_TIME_REAL", "OUT_TIME_REAL", "PLAYER_PTS", "PT_DIFF",
                       "USG_PCT"]
        rot = {"resultSets": [
            {"name": name, "headers": rot_headers,
             "rowSet": [[game_id, team, "X", "Y", p, "F", "L", float(a), float(b), 0, 0, 0.0]
                        for (team, p, a, b) in stints if team == side]}
            for name, side in (("AwayTeam", away), ("HomeTeam", home))]}
        return pbp, rot, self._box_payload(game_id, home, away, stints)

    def _possession(self, act, period, t, offense, defense, off_on, def_on, points, game_id, date):
        rng, box = self.rng, self.box
        r = rng.random()
        if r < 0.13:
            p = int(rng.choice(off_on))
            sub = TOV_TYPES[rng.integers(len(TOV_TYPES))]
            act(period, t, offense, p, "Turnover", sub)
            box[p]["TOV"] += 1
            if sub in ("Bad Pass", "Lost Ball"):
                box[int(rng.choice(def_on))]["STL"] += 1
            return
        if r < 0.25:
            shooter, fouler = int(rng.choice(off_on)), int(rng.choice(def_on))
            box[fouler]["PF"] += 1
            act(period, t, defense, fouler, "Foul", "Shooting")
            for k in (1, 2):
                made = rng.random() < 0.76
                act(period, t, offense, shooter, "Free Throw", f"Free Throw {k} of 2",
                    ("" if made else "MISS ") + f"P{shooter} Free Throw {k} of 2",
                    "Made" if made else "Missed")
                box[shooter]["FTA"] += 1
                box[shooter]["FTM"] += made
                box[shooter]["PTS"] += made
                points[offense] += made
                if k == 2 and not made:
                    reb = int(rng.choice(def_on))
                    act(period, t, defense, reb, "Rebound", "defensive")
                    box[reb]["DREB"] += 1
            return
        for attempt in range(3):
            shooter = int(rng.choice(off_on))
            is3 = rng.random() < 0.38
            made = rng.random() < (0.36 if is3 else 0.52)
            if is3:
                action_type, zone = "Jump Shot", ("Above the Break 3" if rng.random() < 0.7 else "Left Corner 3")
            else:
                action_type, zone = TWO_PT_SHOTS[rng.integers(len(TWO_PT_SHOTS))]
            num = act(period, t + attempt * 20, offense, shooter, "Made Shot" if made else "Missed Shot",
                      action_type, "", "Made" if made else "Missed", 1, 3 if is3 else 2)
            self.shots[offense].append([game_id, num, shooter, offense, action_type, zone, 1,
                                        int(made), date])
            b = box[shooter]
            b["FGA"] += 1
            b["FG3A"] += is3
            b[f"ZONE|{zone}|FGA"] += 1
            if made:
                b["FGM"] += 1
                b["FG3M"] += is3
                b["PTS"] += 3 if is3 else 2
                b[f"ZONE|{zone}|FGM"] += 1
                points[offense] += 3 if is3 else 2
                if self.rng.random() < 0.6:
                    box[int(self.rng.choice([p for p in off_on if p != shooter]))]["AST"] += 1
                return
            if attempt < 2 and self.rng.random() < 0.27:
                reb = int(self.rng.choice(off_on))
                act(period, t + attempt * 20, offense, reb, "Rebound", "offensive")
                box[reb]["OREB"] += 1
                continue
            reb = int(self.rng.choice(def_on))
            act(period, t + attempt * 20, defense, reb, "Rebound", "defensive")
            box[reb]["DREB"] += 1
            return

    def _box_minutes_and_gp(self, game_id, home, away, stints):
        for p in {p for (_t, p, _a, _b) in stints}:
            self.box[p]["GP"] += 1

    def _box_payload(self, game_id, home, away, stints):
        mins = defaultdict(float)
        for (_t, p, a, b) in stints:
            mins[p] += (b - a) / 600

        def team(t):
            players = []
            for k, p in enumerate(self.roster[t]):
                m = mins.get(p, 0.0)
                players.append({"personId": p, "firstName": f"First{p}", "familyName": f"Last{p}",
                                "nameI": "", "playerSlug": "", "position": ("G", "G", "F", "F", "C")[k] if k < 5 else "",
                                "comment": "" if m else "DNP - Coach's Decision", "jerseyNum": str(k),
                                "statistics": {"minutes": f"{int(m)}:{int(round((m % 1) * 60)):02d}" if m else ""}})
            return {"teamId": t, "teamCity": "C", "teamName": "N", "teamTricode": "T", "teamSlug": "s",
                    "players": players, "statistics": {}}
        return {"boxScoreTraditional": {"gameId": game_id, "homeTeam": team(home), "awayTeam": team(away)}}

    # -- league dashboards ---------------------------------------------------
    def played(self):
        return sorted(p for p, b in self.box.items() if b["GP"] > 0)

    def base_totals(self):
        cols = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "GP", "MIN", "FGM", "FGA", "FG3M", "FG3A",
                "FTM", "FTA", "OREB", "DREB", "AST", "TOV", "STL", "BLK", "PF", "PTS"]
        rows = []
        for p in self.played():
            b = self.box[p]
            rows.append([p, f"P{p}", self.team_of[p], b["GP"], self.minutes[p]] +
                        [b[c] for c in cols[5:]])
        return rs("LeagueDashPlayerStats", cols, rows)

    def shot_locations(self):
        cols = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "AGE", "NICKNAME"]
        rows = []
        for p in self.played():
            b = self.box[p]
            row = [p, f"P{p}", self.team_of[p], "T", 25, ""]
            for z in ZONES:
                fga, fgm = b[f"ZONE|{z}|FGA"], b[f"ZONE|{z}|FGM"]
                row += [fgm, fga, fgm / fga if fga else None]
            rows.append(row)
        return {"resultSets": {"name": "ShotLocations", "headers": [
            {"name": "SHOT_CATEGORY", "columnSpan": 3, "columnsToSkip": len(cols), "columnNames": list(ZONES)},
            {"name": "columns", "columnSpan": 1, "columnNames": cols + ["FGM", "FGA", "FG_PCT"] * len(ZONES)},
        ], "rowSet": rows}}

    def split(self, total, k):
        return self.rng.multinomial(int(total), np.ones(k) / k)

    def payloads(self):
        rng, out = self.rng, {}
        played = self.played()
        fga = {p: self.box[p]["FGA"] for p in played}
        mins = {p: self.minutes[p] for p in played}
        names = plan.by_name(plan.all_league_and_team_requests())

        out["player_base_totals"] = self.base_totals()
        out["player_shot_locations"] = self.shot_locations()

        clock_split = {p: self.split(fga[p], len(plan.SHOT_CLOCK_RANGES)) for p in played}
        for i, sc in enumerate(plan.SHOT_CLOCK_RANGES):
            out[plan.shot_clock_name(sc)] = rs("LeagueDashPTShots", ["PLAYER_ID", "FGA"],
                                              [[p, int(clock_split[p][i])] for p in played])
        cs_pu = {p: self.split(fga[p], 3) for p in played}
        out["pt_CatchShoot"] = rs("LeagueDashPtStats", ["PLAYER_ID", "CATCH_SHOOT_FGA"],
                                  [[p, int(cs_pu[p][0])] for p in played])
        out["pt_PullUpShot"] = rs("LeagueDashPtStats", ["PLAYER_ID", "PULL_UP_FGA"],
                                  [[p, int(cs_pu[p][1])] for p in played])
        out["pt_Drives"] = rs("LeagueDashPtStats", ["PLAYER_ID", "DRIVE_FGA", "DRIVE_PASSES"],
                              [[p, int(rng.binomial(fga[p], 0.3)), int(rng.poisson(mins[p] * 0.1))]
                               for p in played])
        passing, poss_rows = [], []
        for p in played:
            passes = int(rng.poisson(mins[p] * 1.0))
            passing.append([p, passes, self.box[p]["AST"] + int(rng.poisson(self.box[p]["AST"] * 0.8))])
            poss_rows.append([p, passes + fga[p] + int(rng.poisson(mins[p] * 0.3))])
        out["pt_Passing"] = rs("LeagueDashPtStats", ["PLAYER_ID", "PASSES_MADE", "POTENTIAL_AST"], passing)
        out["pt_Possessions"] = rs("LeagueDashPtStats", ["PLAYER_ID", "TOUCHES"], poss_rows)
        out["pt_Rebounding"] = rs("LeagueDashPtStats", ["PLAYER_ID", "OREB_CHANCES"],
                                  [[p, self.box[p]["OREB"]] for p in played])
        hustle_cols = ["PLAYER_ID", "CONTESTED_SHOTS", "DEFLECTIONS", "CHARGES_DRAWN",
                       "SCREEN_ASSISTS", "LOOSE_BALLS_RECOVERED", "BOX_OUTS"]
        out["player_hustle"] = rs("HustleStatsPlayer", hustle_cols, [
            [p, int(rng.binomial(int(mins[p] * 1.5), 0.2)), int(rng.binomial(int(mins[p] * 1.5), 0.04)),
             int(rng.binomial(int(mins[p]), 0.004)), int(rng.binomial(int(mins[p]), 0.03)),
             int(rng.binomial(int(mins[p]), 0.02)), int(rng.binomial(int(mins[p]), 0.03))]
            for p in played])
        usage = {p: self.split(fga[p] + self.box[p]["TOV"] + 0.44 * self.box[p]["FTA"], len(plan.PLAY_TYPES))
                 for p in played}
        for i, pt in enumerate(plan.PLAY_TYPES):
            out[plan.play_type_name("offensive", pt)] = rs(
                "SynergyPlayType", ["PLAYER_ID", "TEAM_ID", "POSS", "PTS"],
                [[p, self.team_of[p], int(usage[p][i]), int(usage[p][i] * 0.95)]
                 for p in played if usage[p][i] > 0])
        dpost = []
        for p in played:
            poss = int(rng.poisson(mins[p] * 0.05))
            dpost.append([p, self.team_of[p], poss, int(rng.binomial(poss * 2, 0.47))])
        out[plan.play_type_name("defensive", "Postup")] = rs(
            "SynergyPlayType", ["PLAYER_ID", "TEAM_ID", "POSS", "PTS"], dpost)
        for t in self.teams:
            rows = []
            for p in self.roster[t]:
                if p in mins:
                    rows.append([1, p, int(rng.poisson(mins[p] * 0.3)), int(rng.poisson(mins[p] * 0.1))])
            out[f"matchups_def_{t}"] = rs("SeasonMatchups", ["OFF_PLAYER_ID", "DEF_PLAYER_ID",
                                                             "MATCHUP_FGA", "HELP_FGA"], rows)
            out[f"shot_chart_{t}"] = rs("Shot_Chart_Detail", [
                "GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "ACTION_TYPE", "SHOT_ZONE_BASIC",
                "SHOT_ATTEMPTED_FLAG", "SHOT_MADE_FLAG", "GAME_DATE"], self.shots[t])
            out[f"roster_{t}"] = rs("CommonTeamRoster", [
                "TeamID", "PLAYER_ID", "PLAYER", "NUM", "POSITION", "HEIGHT", "WEIGHT", "BIRTH_DATE", "EXP"],
                [[t, p, f"First{p} Last{p}", str(k), "G" if k < 4 else "F" if k < 8 else "C",
                  f"6-{int(rng.integers(1, 12))}", str(int(rng.integers(180, 260))), "2000-01-01", "3"]
                 for k, p in enumerate(self.roster[t])])
        log_rows = []
        for (gid, date, h, a, hp, ap) in self.games:
            log_rows.append([h, gid, date, f"T{h} vs. T{a}", hp])
            log_rows.append([a, gid, date, f"T{a} @ T{h}", ap])
        out[f"team_game_log_{SEASON}"] = rs("LeagueGameLog", ["TEAM_ID", "GAME_ID", "GAME_DATE",
                                                             "MATCHUP", "PTS"], log_rows)
        for name in ("team_base_totals", "team_advanced_totals"):
            out[name] = rs("LeagueDashTeamStats", ["TEAM_ID", "TEAM_NAME", "GP", "PTS", "PTS_RANK"],
                           [[t, "N", 2, 220.0, 1] for t in self.teams])
        everyone = [p for ps in self.roster.values() for p in ps]
        for year in range(COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR + 1):
            rows = [[p, 76.0 + rng.normal(0, 3)] for p in everyone[::2]] if year == 2020 else []
            out[f"combine_anthro_{year}"] = rs("Results", ["PLAYER_ID", "WINGSPAN"], rows)
        return {names[k]: v for k, v in out.items()}


def write_store(path, seed=0):
    lg = SyntheticLeague(seed)
    store = RawStore(path)
    order = list(range(30))
    pairs = [(order[i], order[i + 1]) for i in range(0, 30, 2)]
    pairs += [(order[i], order[(i + 1) % 30]) for i in range(1, 30, 2)]
    for g, (hi, ai) in enumerate(pairs, 1):
        gid = f"00225{g:05d}"
        date = f"2025-11-{1 + g // 15:02d}"
        pbp, rot, box = lg.play(gid, date, lg.teams[hi], lg.teams[ai])
        for req, payload in zip(plan.game_requests(gid), (pbp, rot, box)):
            store.put(req.endpoint, req.params, payload)
    for req, payload in lg.payloads().items():
        store.put(req.endpoint, req.params, payload)
    store.close()
    return lg
