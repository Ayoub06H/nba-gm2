"""A synthetic raw cache in the exact response shapes stats.nba.com and cdn.nba.com return.

Used to run the full offline build end to end without network access. The
numbers are random but internally consistent: box scores, play-by-play, shot
charts, rotations and every dashboard come from the same simulated games, so
every proportion the build forms stays a valid proportion.

This is test scaffolding only. Nothing here ever reaches the real league file.
"""

from collections import defaultdict

import numpy as np

from nbagm import plan
from nbagm.config import COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR, DURABILITY_SEASONS, SEASON
from nbagm.rawstore import RawStore

PLAYERS_PER_TEAM = 11          # player 11 is rostered but never plays
GAMES_PER_TEAM = 6
V3_ONLY_GAMES = 3              # games with no liveData play-by-play: the build falls back to V3
POSITIONS = ("G", "G-F", "F-G", "F", "F-C", "C-F", "C", "G", "F", "C", "G")

# (ACTION_TYPE, SHOT_ZONE_BASIC, distance range, value, base make probability, general range)
SHOT_TYPES = (
    ("Driving Layup Shot", "Restricted Area", (0, 3), 2, 0.60, "other"),
    ("Driving Dunk Shot", "Restricted Area", (0, 2), 2, 0.90, "other"),
    ("Dunk Shot", "Restricted Area", (0, 2), 2, 0.92, "other"),
    ("Cutting Layup Shot", "Restricted Area", (0, 3), 2, 0.65, "other"),
    ("Floating Jump shot", "In The Paint (Non-RA)", (6, 12), 2, 0.42, "other"),
    ("Hook Shot", "In The Paint (Non-RA)", (5, 10), 2, 0.48, "other"),
    ("Jump Shot", "In The Paint (Non-RA)", (8, 14), 2, 0.40, "Catch and Shoot"),
    ("Pullup Jump shot", "Mid-Range", (12, 22), 2, 0.41, "Pullups"),
    ("Fadeaway Jump Shot", "Mid-Range", (14, 20), 2, 0.39, "Pullups"),
    ("Jump Shot", "Above the Break 3", (23, 27), 3, 0.36, "Catch and Shoot"),
    ("Jump Shot", "Left Corner 3", (22, 23), 3, 0.38, "Catch and Shoot"),
    ("Step Back Jump shot", "Above the Break 3", (24, 28), 3, 0.33, "Pullups"),
)
ZONE_AREAS = {
    "Restricted Area": ("Center(C)",),
    "In The Paint (Non-RA)": ("Center(C)", "Left Side(L)", "Right Side(R)"),
    "Mid-Range": ("Left Side(L)", "Right Side(R)", "Left Side Center(LC)", "Right Side Center(RC)",
                  "Center(C)"),
    "Above the Break 3": ("Left Side Center(LC)", "Right Side Center(RC)", "Center(C)"),
    "Left Corner 3": ("Left Side(L)",),
}
DEF_DIST = plan.CLOSE_DEF_DIST_RANGES[1:]
TOV_TYPES = ("bad pass", "lost ball", "traveling", "offensive foul")


def rs(name, headers, rows):
    return {"resultSets": [{"name": name, "headers": list(headers), "rowSet": [list(r) for r in rows]}]}


def pid(team_index, k):
    return 1_000_000 + team_index * 20 + k


def clock(period, elapsed_tenths):
    remaining = (720 if period <= 4 else 300) * 10 - elapsed_tenths
    return f"PT{remaining // 600:02d}M{(remaining % 600) / 10:05.2f}S"


class SyntheticLeague:
    def __init__(self, seed=0):
        self.rng = rng = np.random.default_rng(seed)
        self.teams = list(plan.TEAM_IDS)
        self.roster = {t: [pid(i, k) for k in range(1, PLAYERS_PER_TEAM + 1)]
                       for i, t in enumerate(self.teams)}
        self.team_of = {p: t for t, ps in self.roster.items() for p in ps}
        self.k_of = {p: k for t, ps in self.roster.items() for k, p in enumerate(ps)}
        everyone = list(self.team_of)
        index = {"G": 1, "G-F": 2, "F-G": 2, "F": 3, "F-C": 4, "C-F": 4, "C": 5}
        self.height = {p: int(72 + 3 * index[POSITIONS[self.k_of[p]]] + rng.integers(0, 4))
                       for p in everyone}
        self.weight = {p: 180 + 4 * (self.height[p] - 74) + int(rng.integers(-10, 15)) for p in everyone}
        self.skill = {p: rng.normal(0, 0.06) for p in everyone}
        self.usage = {p: rng.uniform(0.5, 2.0) for p in everyone}
        self.profile = {p: rng.dirichlet(np.ones(len(SHOT_TYPES)) * 0.8) for p in everyone}
        self.box = defaultdict(lambda: defaultdict(float))         # season totals
        self.game_box = defaultdict(lambda: defaultdict(float))    # (player, game)
        self.onfloor = defaultdict(lambda: defaultdict(float))     # player -> on-floor counts
        self.contest = defaultdict(lambda: defaultdict(float))     # player -> category counts
        self.cells = defaultdict(lambda: defaultdict(float))       # (player, general, dist) -> counts
        self.minutes = defaultdict(float)
        self.shots = defaultdict(list)
        self.games = []

    # -- one game ------------------------------------------------------------
    def lineup(self, team, period, half):
        ps = self.roster[team]
        if half == 0:
            return ps[0:5]
        return [ps[0], ps[1], ps[7], ps[8], ps[9]] if period == 4 else [ps[0], ps[1], ps[2], ps[5], ps[6]]

    def play(self, game_id, date, home, away):
        self.events, self.gid, self.date = [], game_id, date
        stints = []
        points = {home: 0, away: 0}
        for period in range(1, 5):
            base = (period - 1) * 7200
            for team in (home, away):
                first, second = self.lineup(team, period, 0), self.lineup(team, period, 1)
                for p in set(first) | set(second):
                    t_in = base if p in first else base + 3600
                    t_out = base + 7200 if p in second else base + 3600
                    stints.append((team, p, t_in, t_out))
                    self.minutes[p] += (t_out - t_in) / 600
                    self.game_box[(p, game_id)]["MIN"] += (t_out - t_in) / 600
            self.ev(period, 0, "period", sub="start")
            offense = home if period % 2 else away
            for i in range(48):
                t = i * 150 + 70
                half = 0 if t < 3600 else 1
                if i == 24:
                    for team in (home, away):
                        outs = sorted(set(self.lineup(team, period, 0)) - set(self.lineup(team, period, 1)))
                        ins = sorted(set(self.lineup(team, period, 1)) - set(self.lineup(team, period, 0)))
                        self.ev(period, 3600, "sub", team=team, outs=outs, ins=ins)
                defense = away if offense == home else home
                self.possession(period, t, offense, defense, self.lineup(offense, period, half),
                                self.lineup(defense, period, half), points)
                offense = defense
            self.ev(period, 7200, "period", sub="end")
        for p in {p for (_t, p, _a, _b) in stints}:
            self.box[p]["GP"] += 1
        self.games.append((game_id, date, home, away, points[home], points[away]))
        return self.events, stints

    def ev(self, period, t, kind, **kw):
        self.events.append(dict(period=period, t=t, kind=kind, **kw))

    def stat(self, p, key, n=1):
        self.box[p][key] += n
        self.game_box[(p, self.gid)][key] += n

    def floor(self, players, key, n=1):
        for p in players:
            self.onfloor[p][key] += n

    def possession(self, period, t, O, D, off_on, def_on, points):
        rng = self.rng
        r = rng.random()
        if r < 0.02:
            self.ev(period, t, "tov", team=O, person=None, sub="shot clock")
            return
        if r < 0.13:
            p = int(rng.choice(off_on))
            sub = TOV_TYPES[rng.integers(len(TOV_TYPES))]
            if sub == "offensive foul":
                drawer = int(rng.choice(def_on))
                self.stat(p, "PF")
                self.ev(period, t, "foul", team=O, person=p, sub="offensive", desc="charge", drawn=drawer)
                self.box[drawer]["CHARGES"] += 1
            self.ev(period, t, "tov", team=O, person=p, sub=sub)
            self.stat(p, "TOV")
            if sub in ("bad pass", "lost ball"):
                s = int(rng.choice(def_on))
                self.ev(period, t, "steal", team=D, person=s)
                self.stat(s, "STL")
            return
        if r < 0.18:
            fouler, drawn = int(rng.choice(def_on)), int(rng.choice(off_on))
            self.stat(fouler, "PF")
            self.ev(period, t, "foul", team=D, person=fouler, sub="personal", desc="", drawn=drawn)
            t += 30
        elif r < 0.28:
            shooter, fouler = int(rng.choice(off_on)), int(rng.choice(def_on))
            self.stat(fouler, "PF")
            self.box[fouler]["SF"] += 1
            self.ev(period, t, "foul", team=D, person=fouler, sub="personal", desc="shooting", drawn=shooter)
            self.free_throws(period, t, O, D, shooter, 2, off_on, def_on, points)
            return
        for attempt in range(3):
            w = np.array([self.usage[p] for p in off_on])
            shooter = int(rng.choice(off_on, p=w / w.sum()))
            k = rng.choice(len(SHOT_TYPES), p=self.profile[shooter])
            action, zone, (d0, d1), value, base_p, general = SHOT_TYPES[k]
            dist = int(rng.integers(d0, d1 + 1))
            made = rng.random() < np.clip(base_p + self.skill[shooter], 0.05, 0.97)
            defender = int(rng.choice(def_on))
            num = self.ev_shot(period, t + attempt * 20, O, D, shooter, action, zone, dist, value, made,
                               defender, general, off_on, def_on)
            if made:
                points[O] += value
                if rng.random() < 0.6:
                    a = int(rng.choice([p for p in off_on if p != shooter]))
                    self.events[num]["assist"] = a
                    self.stat(a, "AST")
                if rng.random() < 0.05:
                    fouler = int(rng.choice(def_on))
                    self.stat(fouler, "PF")
                    self.box[fouler]["SF"] += 1
                    self.ev(period, t + attempt * 20, "foul", team=D, person=fouler, sub="personal",
                            desc="shooting", drawn=shooter)
                    self.free_throws(period, t + attempt * 20, O, D, shooter, 1, off_on, def_on, points)
                return
            if rng.random() < 0.07:
                b = int(rng.choice(def_on))
                self.events[num]["blocker"] = b
                self.ev(period, t + attempt * 20, "block", team=D, person=b)
                self.stat(b, "BLK")
            if attempt == 2:
                self.ev(period, t + attempt * 20, "reb", team=D, person=None, sub="defensive")
                return
            if rng.random() < 0.27:
                reb = int(rng.choice(off_on))
                self.ev(period, t + attempt * 20, "reb", team=O, person=reb, sub="offensive")
                self.stat(reb, "OREB")
                continue
            reb = int(rng.choice(def_on))
            self.ev(period, t + attempt * 20, "reb", team=D, person=reb, sub="defensive")
            self.stat(reb, "DREB")
            return

    def ev_shot(self, period, t, O, D, shooter, action, zone, dist, value, made, defender, general,
                off_on, def_on):
        rng = self.rng
        self.ev(period, t, "fga", team=O, person=shooter, value=value, made=made, dist=dist,
                action=action)
        num = len(self.events) - 1
        area = ZONE_AREAS[zone][rng.integers(len(ZONE_AREAS[zone]))]
        loc_x = int(rng.choice([-1, 1]) * min(dist, 22) * 10 * rng.uniform(0.2, 1.0))
        rem = (7200 - t) // 10
        self.shots[O].append([self.gid, None, shooter, O, period, int(rem // 60), int(rem % 60), action,
                              f"{value}PT Field Goal", zone, area, dist, loc_x, dist * 8, 1, int(made),
                              self.date.replace("-", ""), num])
        self.stat(shooter, "FGA")
        self.stat(shooter, "FGM", made)
        self.stat(shooter, "PTS", value * made)
        if value == 3:
            self.stat(shooter, "FG3A")
            self.stat(shooter, "FG3M", made)
        self.floor(off_on, "team_fga")
        self.floor(def_on, "opp_fga")
        if not made:
            self.floor(off_on, "team_missed_fga")
            self.floor(def_on, "opp_missed")
        cat = "P3" if value == 3 else ("R" if dist < 6 else "P2")
        self.contest[defender][cat + "_A"] += 1
        self.contest[defender][cat + "_M"] += made
        dd = DEF_DIST[rng.integers(len(DEF_DIST))]
        c = self.cells[(shooter, general, dd)]
        c["FGA"] += 1
        if value == 3:
            c["FG3A"] += 1
            c["FG3M"] += made
        return num

    def free_throws(self, period, t, O, D, shooter, n, off_on, def_on, points):
        rng = self.rng
        for k in range(1, n + 1):
            made = rng.random() < 0.76 + self.skill[shooter]
            self.ev(period, t, "fta", team=O, person=shooter, sub=f"{k} of {n}", made=made)
            self.stat(shooter, "FTA")
            self.stat(shooter, "FTM", made)
            self.stat(shooter, "PTS", made)
            points[O] += made
            if k == n and not made:
                self.floor(def_on, "opp_missed")
                reb = int(rng.choice(def_on))
                self.ev(period, t, "reb", team=D, person=reb, sub="defensive")
                self.stat(reb, "DREB")

    # -- serialization -------------------------------------------------------
    def to_live(self, events):
        acts, n = [], 0

        def add(e, **kw):
            nonlocal n
            n += 1
            a = {"actionNumber": n, "clock": clock(e["period"], e["t"]), "period": e["period"],
                 "teamId": e.get("team"), "personId": e.get("person") or 0, **kw}
            if a["personId"]:
                a["playerName"], a["playerNameI"] = f"Last{a['personId']}", f"F. Last{a['personId']}"
            acts.append(a)
            return n

        for e in events:
            k = e["kind"]
            if k == "period":
                add(e, actionType="period", subType=e["sub"])
            elif k == "sub":
                for p in e["outs"]:
                    add(dict(e, person=p), actionType="substitution", subType="out")
                for p in e["ins"]:
                    add(dict(e, person=p), actionType="substitution", subType="in")
            elif k == "fga":
                extra = {"assistPersonId": e["assist"]} if e.get("assist") else {}
                if e.get("blocker"):
                    extra["blockPersonId"] = e["blocker"]
                e["event_id"] = add(e, actionType=f"{e['value']}pt", subType=e["action"],
                                    shotResult="Made" if e["made"] else "Missed",
                                    shotDistance=float(e["dist"]) + 0.3, isFieldGoal=1, **extra)
            elif k == "fta":
                add(e, actionType="freethrow", subType=e["sub"], shotResult="Made" if e["made"] else "Missed")
            elif k == "reb":
                add(e, actionType="rebound", subType=e["sub"])
            elif k == "tov":
                add(e, actionType="turnover", subType=e["sub"])
            elif k == "foul":
                add(e, actionType="foul", subType=e["sub"], descriptor=e["desc"],
                    foulDrawnPersonId=e["drawn"])
            elif k in ("steal", "block"):
                add(e, actionType=k)
        return {"game": {"gameId": self.gid, "actions": acts}}

    def to_v3(self, events):
        rows, n = [], 0

        def add(e, at, sub="", desc="", result="", fg=0, value=0, team=None, person=None, dist=None):
            nonlocal n
            n += 1
            p = e.get("person") if person is None else person
            rows.append({"actionNumber": n, "clock": clock(e["period"], e["t"]), "period": e["period"],
                         "teamId": e.get("team") if team is None else team, "personId": p or 0,
                         "playerName": f"Last{p}" if p else "", "actionType": at, "subType": sub,
                         "description": desc, "shotResult": result, "isFieldGoal": fg,
                         "shotValue": value, "shotDistance": dist})
            return n

        for e in events:
            k = e["kind"]
            if k == "period":
                add(e, "period", e["sub"], team=0, person=0)
            elif k == "sub":
                for o, i in zip(e["outs"], e["ins"]):
                    add(e, "Substitution", desc=f"SUB: Last{i} FOR Last{o}", person=o)
            elif k == "fga":
                desc = f"Last{e['person']} {e['action']}"
                if e.get("assist"):
                    desc += f" (Last{e['assist']} 1 AST)"
                e["event_id"] = add(e, "Made Shot" if e["made"] else "Missed Shot", e["action"], desc,
                                    "Made" if e["made"] else "Missed", 1, e["value"], dist=e["dist"])
                if e.get("blocker"):
                    add(e, "", desc=f"Last{e['blocker']} BLOCK (1 BLK)", team=e["team"],
                        person=e["blocker"])
            elif k == "fta":
                add(e, "Free Throw", f"Free Throw {e['sub']}",
                    ("" if e["made"] else "MISS ") + f"Last{e['person']} Free Throw {e['sub']}",
                    "Made" if e["made"] else "Missed")
            elif k == "reb":
                if e.get("person"):
                    add(e, "Rebound", "Unknown", f"Last{e['person']} REBOUND")
                else:
                    add(e, "Rebound", "Unknown", "Team Rebound", team=0, person=e["team"])
            elif k == "tov":
                sub = {"bad pass": "Bad Pass", "lost ball": "Lost Ball", "traveling": "Traveling",
                       "offensive foul": "Offensive Foul", "shot clock": "Shot Clock"}[e["sub"]]
                if e.get("person"):
                    add(e, "Turnover", sub, f"Last{e['person']} {sub} Turnover")
                else:
                    add(e, "Turnover", sub, f"Team Turnover: {sub}", team=0, person=e["team"])
            elif k == "foul":
                sub = {"offensive": "Offensive Charge", "personal": "Shooting" if e["desc"] == "shooting"
                       else "Personal"}[e["sub"]]
                add(e, "Foul", sub, f"Last{e['person']} {sub} foul")
            elif k == "steal":
                add(e, "", desc=f"Last{e['person']} STEAL (1 STL)")
        return {"game": {"gameId": self.gid, "actions": rows}}

    def shot_chart_rows(self, events):
        """Shot chart GAME_EVENT_ID = the play-by-play action number of the same shot."""
        for team_rows in self.shots.values():
            for row in team_rows:
                if row[0] == self.gid and row[1] is None:
                    row[1] = events[row[-1]]["event_id"]

    def box_payload(self, game_id, home, away, stints, inactive=()):
        mins = defaultdict(float)
        for (_t, p, a, b) in stints:
            mins[p] += (b - a) / 600

        def team(t):
            players = []
            for k, p in enumerate(self.roster[t]):
                if p in inactive:
                    continue
                m = mins.get(p, 0.0)
                players.append({"personId": p, "firstName": f"First{p}", "familyName": f"Last{p}",
                                "nameI": f"F. Last{p}", "playerSlug": "", "position": POSITIONS[k] if k < 5 else "",
                                "comment": "" if m else "DNP - Coach's Decision", "jerseyNum": str(k),
                                "statistics": {"minutes": f"{int(m)}:{int(round((m % 1) * 60)):02d}" if m else ""}})
            return {"teamId": t, "teamCity": "C", "teamName": "N", "teamTricode": "T", "teamSlug": "s",
                    "players": players, "statistics": {}}
        return {"boxScoreTraditional": {"gameId": game_id, "homeTeam": team(home), "awayTeam": team(away)}}

    def summary_payload(self, game_id, home, away, inactive):
        def team(t):
            return {"teamId": t, "inactives": [{"personId": p, "firstName": "F", "familyName": f"Last{p}",
                                                "jerseyNum": "0"} for p in inactive if self.team_of[p] == t]}
        return {"boxScoreSummary": {"gameId": game_id, "homeTeam": team(home), "awayTeam": team(away)}}

    def rotation_payload(self, game_id, home, away, stints):
        headers = ["GAME_ID", "TEAM_ID", "TEAM_CITY", "TEAM_NAME", "PERSON_ID", "PLAYER_FIRST",
                   "PLAYER_LAST", "IN_TIME_REAL", "OUT_TIME_REAL", "PLAYER_PTS", "PT_DIFF", "USG_PCT"]
        return {"resultSets": [
            {"name": name, "headers": headers,
             "rowSet": [[game_id, team, "X", "Y", p, "F", "L", float(a), float(b), 0, 0, 0.0]
                        for (team, p, a, b) in stints if team == side]}
            for name, side in (("AwayTeam", away), ("HomeTeam", home))]}

    # -- league dashboards ---------------------------------------------------
    def played(self):
        return sorted(p for p, b in self.box.items() if b["GP"] > 0)

    def binom(self, n, p):
        return int(self.rng.binomial(max(int(n), 0), p))

    def payloads(self):
        rng, out = self.rng, {}
        played = self.played()
        B = self.box
        names = plan.by_name(plan.all_league_and_team_requests())

        cols = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "GP", "MIN", "FGM", "FGA", "FG3M", "FG3A",
                "FTM", "FTA", "OREB", "DREB", "AST", "TOV", "STL", "BLK", "PF", "PTS"]
        out["player_base_totals"] = rs("LeagueDashPlayerStats", cols, [
            [p, f"P{p}", self.team_of[p], B[p]["GP"], self.minutes[p]] + [B[p][c] for c in cols[5:]]
            for p in played])
        clutch = []
        for p in played:
            fga, fta = self.binom(B[p]["FGA"], 0.1), self.binom(B[p]["FTA"], 0.1)
            clutch.append([p, self.binom(2 * fga + fta, 0.5), fga, fta])
        out["player_clutch_base"] = rs("LeagueDashPlayerClutch", ["PLAYER_ID", "PTS", "FGA", "FTA"], clutch)

        sc_rows = {sc: [] for sc in plan.SHOT_CLOCK_RANGES}
        for p in played:
            split = rng.multinomial(int(B[p]["FGA"]), np.ones(len(plan.SHOT_CLOCK_RANGES)) / len(plan.SHOT_CLOCK_RANGES))
            for sc, n in zip(plan.SHOT_CLOCK_RANGES, split):
                sc_rows[sc].append([p, int(n)])
        for sc, rows in sc_rows.items():
            out[plan.shot_clock_name(sc)] = rs("LeagueDashPTShots", ["PLAYER_ID", "FGA"], rows)
        shot_cols = ["PLAYER_ID", "FGA", "FG3M", "FG3A"]
        for g in ("Catch and Shoot", "Pullups"):
            for d in DEF_DIST:
                out[plan.pt_shot_name(g, d, "")] = rs("LeagueDashPTShots", shot_cols, [
                    [p, self.cells[(p, g, d)]["FGA"], self.cells[(p, g, d)]["FG3M"], self.cells[(p, g, d)]["FG3A"]]
                    for p in played])
            out[plan.pt_shot_name(g, "", "")] = rs("LeagueDashPTShots", shot_cols, [
                [p] + [sum(self.cells[(p, g, d)][c] for d in DEF_DIST) for c in ("FGA", "FG3M", "FG3A")]
                for p in played])

        drives, passing, poss_rows, reb, speed, hustle = [], [], [], [], [], []
        for p in played:
            b, f, m = B[p], self.onfloor[p], self.minutes[p]
            d_fga = self.binom(b["FGA"], 0.3)
            drives.append([p, d_fga + self.binom(m, 0.1), d_fga, self.binom(m, 0.1), self.binom(b["FTA"], 0.3)])
            passes = int(rng.poisson(m * 1.0)) + 1
            pot = int(b["AST"]) + self.binom(passes, 0.05)
            passing.append([p, passes, pot, b["AST"] + self.binom(b["AST"], 0.2), self.binom(b["AST"], 0.1),
                            self.binom(b["AST"], 0.1), 2.3 * b["AST"]])
            poss_rows.append([p, passes + b["FGA"] + self.binom(m, 0.3), rng.uniform(0.5, 4.0)])
            oc = b["OREB"] + self.binom(f["team_missed_fga"] - b["OREB"], 0.2)
            dc = b["DREB"] + self.binom(f["opp_missed"] - b["DREB"], 0.2)
            reb.append([p, b["OREB"], b["DREB"], oc, dc, self.binom(oc - b["OREB"], 0.3),
                        self.binom(dc - b["DREB"], 0.3)])
            speed.append([p, m, rng.normal(4.6, 0.2), rng.normal(4.1, 0.2), m * 0.045 * rng.uniform(0.9, 1.1),
                          m * 0.04 * rng.uniform(0.9, 1.1)])
            olb, dlb = self.binom(m, 0.01), self.binom(m, 0.01)
            sa = self.binom(m, 0.03)
            hustle.append([p, self.binom(f["opp_fga"], 0.25), self.binom(f["opp_fga"] // 3, 0.1),
                           b["CHARGES"], sa, 2.4 * sa, olb, dlb, olb + dlb, self.binom(f["team_missed_fga"], 0.05),
                           self.binom(f["opp_missed"], 0.1)])
        out["pt_Drives"] = rs("LeagueDashPtStats", ["PLAYER_ID", "DRIVES", "DRIVE_FGA", "DRIVE_PASSES", "DRIVE_FTA"], drives)
        out["pt_Passing"] = rs("LeagueDashPtStats", ["PLAYER_ID", "PASSES_MADE", "POTENTIAL_AST", "AST_ADJ",
                                                     "FT_AST", "SECONDARY_AST", "AST_POINTS_CREATED"], passing)
        out["pt_Possessions"] = rs("LeagueDashPtStats", ["PLAYER_ID", "TOUCHES", "AVG_DRIB_PER_TOUCH"], poss_rows)
        out["pt_Rebounding"] = rs("LeagueDashPtStats", ["PLAYER_ID", "OREB", "DREB", "OREB_CHANCES", "DREB_CHANCES",
                                                        "OREB_CHANCE_DEFER", "DREB_CHANCE_DEFER"], reb)
        out["pt_SpeedDistance"] = rs("LeagueDashPtStats", ["PLAYER_ID", "MIN", "AVG_SPEED_OFF", "AVG_SPEED_DEF",
                                                           "DIST_MILES_OFF", "DIST_MILES_DEF"], speed)
        out["player_hustle"] = rs("HustleStatsPlayer", [
            "PLAYER_ID", "CONTESTED_SHOTS", "DEFLECTIONS", "CHARGES_DRAWN", "SCREEN_ASSISTS", "SCREEN_AST_PTS",
            "OFF_LOOSE_BALLS_RECOVERED", "DEF_LOOSE_BALLS_RECOVERED", "LOOSE_BALLS_RECOVERED", "OFF_BOXOUTS",
            "DEF_BOXOUTS"], hustle)

        usage = {p: rng.multinomial(int(B[p]["FGA"] + B[p]["TOV"] + 0.44 * B[p]["FTA"]) + 1,
                                    rng.dirichlet(np.ones(len(plan.PLAY_TYPES))))
                 for p in played}
        for i, pt in enumerate(plan.PLAY_TYPES):
            out[plan.play_type_name("offensive", pt)] = rs(
                "SynergyPlayType", ["PLAYER_ID", "TEAM_ID", "POSS", "PTS"],
                [[p, self.team_of[p], int(usage[p][i]), self.binom(3 * usage[p][i], 0.33)]
                 for p in played if usage[p][i] > 0])
        dpost = []
        for p in played:
            poss = int(rng.poisson(self.minutes[p] * 0.05))
            dpost.append([p, self.team_of[p], poss, self.binom(poss * 2, 0.47)])
        out[plan.play_type_name("defensive", "Postup")] = rs(
            "SynergyPlayType", ["PLAYER_ID", "TEAM_ID", "POSS", "PTS"], dpost)

        q = {"P3": 0.36, "R": 0.62, "P2": 0.42}
        cats = {"Overall": [], "3 Pointers": [], "2 Pointers": [], "Less Than 6Ft": []}
        for p in played:
            c = self.contest[p]
            a3, m3, ar, mr, a2, m2 = (c[k] for k in ("P3_A", "P3_M", "R_A", "R_M", "P2_A", "P2_M"))
            all_a, all_m = a3 + ar + a2, m3 + mr + m2
            qn = (a3 * q["P3"] + ar * q["R"] + a2 * q["P2"]) / all_a if all_a else None
            cats["Overall"].append([p, all_m, all_a, all_m / all_a if all_a else None, qn,
                                    (all_m / all_a - qn) if all_a else None])
            cats["3 Pointers"].append([p, m3, a3, q["P3"]])
            q2 = (ar * q["R"] + a2 * q["P2"]) / (ar + a2) if ar + a2 else None
            cats["2 Pointers"].append([p, mr + m2, ar + a2, q2])
            cats["Less Than 6Ft"].append([p, mr, ar, q["R"]])
        out[plan.pt_defend_name("Overall")] = rs("LeagueDashPTDefend", [
            "CLOSE_DEF_PERSON_ID", "D_FGM", "D_FGA", "D_FG_PCT", "NORMAL_FG_PCT", "PCT_PLUSMINUS"], cats["Overall"])
        out[plan.pt_defend_name("3 Pointers")] = rs("LeagueDashPTDefend", [
            "CLOSE_DEF_PERSON_ID", "FG3M", "FG3A", "NS_FG3_PCT"], cats["3 Pointers"])
        out[plan.pt_defend_name("2 Pointers")] = rs("LeagueDashPTDefend", [
            "CLOSE_DEF_PERSON_ID", "FG2M", "FG2A", "NS_FG2_PCT"], cats["2 Pointers"])
        out[plan.pt_defend_name("Less Than 6Ft")] = rs("LeagueDashPTDefend", [
            "CLOSE_DEF_PERSON_ID", "FGM_LT_06", "FGA_LT_06", "NS_LT_06_PCT"], cats["Less Than 6Ft"])

        gl_cols = ["PLAYER_ID", "GAME_ID", "GAME_DATE", "MIN", "PTS", "FGM", "FGA", "FTM", "FTA", "OREB",
                   "DREB", "STL", "AST", "BLK", "PF", "TOV"]
        dates = {g[0]: g[1] for g in self.games}
        out[f"player_game_logs_{SEASON}"] = rs("PlayerGameLogs", gl_cols, [
            [p, g, dates[g], s["MIN"]] + [s[c] for c in gl_cols[4:]]
            for (p, g), s in self.game_box.items() if s["MIN"] > 0])

        for t in self.teams:
            out[f"shot_chart_{t}"] = rs("Shot_Chart_Detail", [
                "GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "TEAM_ID", "PERIOD", "MINUTES_REMAINING",
                "SECONDS_REMAINING", "ACTION_TYPE", "SHOT_TYPE", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA",
                "SHOT_DISTANCE", "LOC_X", "LOC_Y", "SHOT_ATTEMPTED_FLAG", "SHOT_MADE_FLAG", "GAME_DATE"],
                [r[:-1] for r in self.shots[t]])
            out[f"roster_{t}"] = rs("CommonTeamRoster", [
                "TeamID", "PLAYER_ID", "PLAYER", "NUM", "POSITION", "HEIGHT", "WEIGHT", "BIRTH_DATE", "AGE", "EXP"],
                [[t, p, f"First{p} Last{p}", str(k), POSITIONS[k],
                  f"{self.height[p] // 12}-{self.height[p] % 12}", str(self.weight[p]), "2000-01-01",
                  float(20 + (p % 13)), "3"]
                 for k, p in enumerate(self.roster[t])])
        everyone = [p for ps in self.roster.values() for p in ps]
        out["player_index"] = rs("PlayerIndex", ["PERSON_ID", "HEIGHT", "WEIGHT"],
                                 [[p, f"{self.height[p] // 12}-{self.height[p] % 12}", str(self.weight[p])]
                                  for p in everyone])
        rows_ = out[f"roster_{self.teams[0]}"]["resultSets"][0]["rowSet"]
        rows_[0][6] = ""          # a roster row with no listed weight, like four real players

        log_rows = []
        for k, (gid, date, h, a, hp, ap) in enumerate(self.games):
            # the first game mimics a neutral-site listing: both rows say "vs."
            log_rows.append([h, gid, date, f"T{h} vs. T{a}", hp])
            log_rows.append([a, gid, date, f"T{a} {'vs.' if k == 0 else '@'} T{h}", ap])
        out[f"team_game_log_{SEASON}"] = rs("LeagueGameLog", ["TEAM_ID", "GAME_ID", "GAME_DATE", "MATCHUP", "PTS"],
                                            log_rows)
        for season, glist in self.old_games.items():
            out[f"team_game_log_{season}"] = rs(
                "LeagueGameLog", ["TEAM_ID", "GAME_ID", "GAME_DATE", "MATCHUP", "PTS"],
                [r for (gid, h, a) in glist for r in ([h, gid, "2024-01-01", "x", 100],
                                                     [a, gid, "2024-01-01", "x", 99])])
        for season in DURABILITY_SEASONS:
            if season not in (SEASON, *self.old_games):
                raise AssertionError(season)
        out["team_base_totals"] = rs("LeagueDashTeamStats", ["TEAM_ID", "TEAM_NAME", "GP", "PTS", "PTS_RANK"],
                                     [[t, "N", GAMES_PER_TEAM, 660.0, 1] for t in self.teams])
        out["team_advanced_totals"] = rs("LeagueDashTeamStats", ["TEAM_ID", "TEAM_NAME", "PACE", "OFF_RATING"],
                                         [[t, "N", float(rng.normal(99, 2)), 112.0] for t in self.teams])
        drills = ["PLAYER_ID", "THREE_QUARTER_SPRINT", "LANE_AGILITY_TIME", "MODIFIED_LANE_AGILITY_TIME",
                  "MAX_VERTICAL_LEAP", "STANDING_VERTICAL_LEAP", "BENCH_PRESS"]
        for year in range(COMBINE_FIRST_YEAR, COMBINE_LAST_YEAR + 1):
            measured = everyone[::2] if year == 2020 else everyone[1::7] if year == 2021 else []
            out[f"combine_anthro_{year}"] = rs("Results", ["PLAYER_ID", "WINGSPAN"],
                                               [[p, self.height[p] * 1.05 + rng.normal(0, 1.5)] for p in measured])
            out[f"combine_drills_{year}"] = rs("Results", drills, [
                [p, 3.3 + 0.01 * (self.height[p] - 78) + rng.normal(0, 0.08),
                 11.2 + 0.03 * (self.height[p] - 78) + rng.normal(0, 0.3),
                 3.1 + 0.01 * (self.height[p] - 78) + rng.normal(0, 0.1),
                 34 - 0.3 * (self.height[p] - 78) + rng.normal(0, 2),
                 28 - 0.3 * (self.height[p] - 78) + rng.normal(0, 2),
                 None if p % 5 == 0 else max(0, int(8 + 0.05 * (self.weight[p] - 220) + rng.normal(0, 3)))]
                for p in measured])
        return {names[k]: v for k, v in out.items()}


def write_store(path, seed=0):
    lg = SyntheticLeague(seed)
    store = RawStore(path)
    rng = lg.rng
    g = 0
    for rnd in range(GAMES_PER_TEAM):
        order = list(rng.permutation(30))
        for i in range(0, 30, 2):
            g += 1
            gid = f"00225{g:05d}"
            date = f"2025-11-{1 + rnd:02d}"
            home, away = lg.teams[order[i]], lg.teams[order[i + 1]]
            events, stints = lg.play(gid, date, home, away)
            # the shot chart's GAME_EVENT_ID must match the play-by-play the build reads
            v3, live = lg.to_v3(events), lg.to_live(events)
            if g <= V3_ONLY_GAMES:
                v3 = lg.to_v3(events)
            lg.shot_chart_rows(events)
            # player 11 sits: in the box score with a DNP comment, or on the inactive list
            sitting = [lg.roster[t][10] for t in (home, away)]
            inactive = sitting if g % 2 else []
            payload = {
                "playbyplayv3": v3,
                "gamerotation": lg.rotation_payload(gid, home, away, stints),
                "boxscoretraditionalv3": lg.box_payload(gid, home, away, stints, inactive),
                "live.playbyplay": live,
                "boxscoresummaryv3": lg.summary_payload(gid, home, away, inactive),
            }
            for req in plan.game_requests(gid):
                if req.endpoint == "gamerotation" and g % 4:
                    continue   # like stats.nba.com, rotation is missing for most games
                if req.endpoint == "live.playbyplay" and g <= V3_ONLY_GAMES:
                    continue   # liveData missing: the build falls back to PlayByPlayV3
                store.put(req.endpoint, req.params, payload[req.endpoint])
    # earlier seasons of the Durability window: appearances, DNP comments, inactive lists
    lg.old_games = {}
    for s_i, season in enumerate(s for s in DURABILITY_SEASONS if s != SEASON):
        glist = []
        for k in range(15):
            gid = f"0022{3 + s_i}{k + 1:05d}"
            home, away = lg.teams[2 * k], lg.teams[2 * k + 1]
            glist.append((gid, home, away))
            players = lg.roster[home] + lg.roster[away]
            inactive = [p for p in players if rng.random() < 0.08]
            stints = [(lg.team_of[p], p, 0, 14400) for p in players if p not in inactive and rng.random() < 0.85]
            box = lg.box_payload(gid, home, away, stints, inactive)
            for team in box["boxScoreTraditional"].values():
                if isinstance(team, dict):
                    for pl in team["players"]:
                        if pl["comment"] and rng.random() < 0.5:
                            pl["comment"] = "DNP - Injury/Illness"
            reqs = plan.durability_game_requests(gid)
            store.put(reqs[0].endpoint, reqs[0].params, box)
            store.put(reqs[1].endpoint, reqs[1].params, lg.summary_payload(gid, home, away, inactive))
        lg.old_games[season] = glist
    for req, payload in lg.payloads().items():
        store.put(req.endpoint, req.params, payload)
    store.close()
    return lg
