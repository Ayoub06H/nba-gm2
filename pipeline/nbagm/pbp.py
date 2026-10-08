"""Play-by-play accounting: lineups, on-floor counts, stints and per-player events.

Two sources feed one engine through small adapters that turn each into the same
event list:
  * cdn.nba.com liveData (primary, doc 11): explicit substitution in/out ids and
    assist/block/steal/foul-drawn ids, and the team in possession;
  * stats.nba.com PlayByPlayV3 (backup): substitutions give only the outgoing id
    ("SUB: <in> FOR <out>"), steals and blocks are separate blank-type rows.

Lineups:
  * Q1 starters come from the box score (starters carry a position).
  * Later periods' starters are not logged: they come from gamerotation when that
    response exists, otherwise from the first players seen acting in the period
    before being subbed in, completed if needed from the previous period's closing
    lineup.
  * A team whose lineup can't be resolved to exactly five players has its events
    skipped (counted in GameAccount.events_unresolved) instead of guessed; the
    lineup is rebuilt from what happens next.

Possessions use the standard estimate FGA - OREB + TOV + 0.44*FTA applied to the
on-floor counts (offense: own team's events; defense: the opponent's).
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

ON_COURT_FIELDS = (
    "team_fga", "team_fgm", "team_missed_fga", "team_fta", "team_oreb", "team_dreb", "team_tov",
    "opp_fga", "opp_fg2a", "opp_missed_fga", "opp_fta", "opp_oreb", "opp_dreb", "opp_tov",
    "opp_missed_final_ft",
)
PLAYER_EVENT_FIELDS = (
    "pbp_blocks", "pbp_blocks_R", "pbp_blocks_P2", "pbp_blocks_P3", "pbp_blocks_recovered",
    "shooting_fouls", "offensive_fouls_drawn", "nonshooting_def_fouls",
    "tov_handling", "tov_bad_pass", "tov_decision",
)

_CLOCK = re.compile(r"PT(\d+)M(\d+(?:\.\d+)?)S")
_FT_OF = re.compile(r"(\d+) of (\d+)")
_SUB = re.compile(r"^SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$")
_AST = re.compile(r"\(([^()]+?) \d+ AST\)")


def _int(x):
    """int for real ids; None for missing values (None, NaN, '', 0)."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or x == "":
        return None
    v = int(x)
    return v or None


def _str(x):
    """Text field; None and NaN (a key missing from some rows of a DataFrame) are ''."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return str(x)


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def period_start(period):
    return (period - 1) * 7200 if period <= 4 else 28800 + (period - 5) * 3000


def period_end(period):
    return period_start(period) + (7200 if period <= 4 else 3000)


def clock_tenths(clock, period):
    """Elapsed game time in integer tenths of a second for a v3/liveData clock string."""
    m = _CLOCK.fullmatch(str(clock))
    if not m:
        raise ValueError(f"unparseable clock {clock!r}")
    remaining = int(m.group(1)) * 60 + float(m.group(2))
    return period_end(period) - int(round(remaining * 10))


def is_reboundable_final_ft(sub_type):
    """Last free throw of a regular trip (e.g. '2 of 2'): the only FT whose miss is live.
    Technical, flagrant and clear-path free throws do not end in a rebound."""
    s = str(sub_type).lower()
    m = _FT_OF.search(s)
    return bool(m) and not any(w in s for w in ("flagrant", "clear path", "technical")) \
        and m.group(1) == m.group(2)


HANDLING_TURNOVERS = ("lost ball", "travel", "double dribble", "discontinued dribble", "palming")


class TurnoverTypeError(ValueError):
    pass


def turnover_class(sub_type):
    """Doc 02 turnover taxonomy: 'bad_pass', 'handling', or 'decision' (every other type).
    A turnover with no type at all cannot be assigned, so it is an error."""
    s = re.sub(r"[\s\-]+", " ", str(sub_type).lower()).strip()
    if not s:
        raise TurnoverTypeError("turnover with no type")
    if "bad pass" in s:
        return "bad_pass"
    if any(h in s for h in HANDLING_TURNOVERS):
        return "handling"
    return "decision"


def shot_category(value, distance):
    """Doc 02 contest categories: R = rim (< 6 ft), P3 = threes, P2 = other twos."""
    if value == 3:
        return "P3"
    if distance is not None and np.isfinite(distance) and distance < 6:
        return "R"
    return "P2"


# --------------------------------------------------------------------------- #
# Normalized events
# --------------------------------------------------------------------------- #

@dataclass
class Ev:
    i: int
    period: int
    clock: str
    t: int
    kind: str                 # fga fta reb tov foul steal block jump violation sub period other
    team: int = None
    person: int = None
    sub: str = ""             # lower-case subtype
    made: bool = False
    value: int = 0
    distance: float = None
    event_id: int = None
    assist: int = None
    assist_name: str = None
    blocker: int = None
    ft_n: int = 0
    ft_of: int = 0
    drawn: int = None
    possession: int = None
    outs: list = field(default_factory=list)
    ins: list = field(default_factory=list)
    in_names: list = field(default_factory=list)


def events_from_v3(rows, teams):
    """stats.nba.com PlayByPlayV3 rows -> events."""
    evs = []
    for i, r in enumerate(rows):
        period, clock = int(r["period"]), r["clock"]
        e = Ev(i, period, clock, clock_tenths(clock, period), "other")
        at = _str(r.get("actionType"))
        sub = _str(r.get("subType"))
        desc = _str(r.get("description"))
        tid, pid = _int(r.get("teamId")), _int(r.get("personId"))
        e.team = tid if tid in teams else (pid if pid in teams else None)
        e.person = pid if pid is not None and pid not in teams else None
        e.sub = sub.lower()
        if _int(r.get("isFieldGoal")) == 1 or at == "Heave":
            sv = _int(r.get("shotValue"))
            e.kind = "fga"
            e.value = sv if sv in (2, 3) else (3 if "3PT" in desc.upper() else 2)
            e.made = r.get("shotResult") == "Made" or at == "Made Shot"
            dist = _str(r.get("shotDistance"))
            e.distance = float(dist) if dist else None
            e.event_id = _int(r.get("actionNumber"))
            m = _AST.search(desc)
            e.assist_name = m.group(1) if (m and e.made) else None
        elif at == "Free Throw":
            e.kind = "fta"
            m = _FT_OF.search(sub)
            e.ft_n, e.ft_of = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            res = r.get("shotResult")
            e.made = res == "Made" if res in ("Made", "Missed") else not desc.upper().startswith("MISS")
        elif at == "Rebound":
            e.kind = "reb"
        elif at == "Turnover":
            if "no turnover" in e.sub:
                continue
            e.kind = "tov"
        elif at == "Foul":
            e.kind = "foul"
        elif at == "":
            up = desc.upper()
            e.kind = "steal" if "STEAL" in up else "block" if "BLOCK" in up else "other"
            if e.kind == "block":
                # V3 logs the blocker on his own row right after the missed shot
                for prev in reversed(evs):
                    if prev.kind == "fga":
                        if not prev.made and prev.period == period and prev.blocker is None:
                            prev.blocker = e.person
                        break
        elif at == "Substitution":
            e.kind = "sub"
            m = _SUB.match(desc)
            e.outs = [e.person] if e.person else []
            e.in_names = [m.group(1)] if m else []
        elif at == "Jump Ball":
            e.kind = "jump"
        elif at == "Violation":
            e.kind = "violation"
        elif at == "period":
            e.kind = "period"
        evs.append(e)
    return evs


def events_from_live(actions, teams):
    """cdn.nba.com liveData actions -> events. Consecutive substitution actions of one
    team at one clock are merged into a single swap."""
    evs = []
    for i, a in enumerate(actions):
        period, clock = int(a["period"]), a["clock"]
        e = Ev(i, period, clock, clock_tenths(clock, period), "other")
        at = _str(a.get("actionType")).lower()
        # liveData splits a type into subType + descriptor ("personal" + "shooting",
        # "out-of-bounds" + "bad pass"); both are kept so the classifiers see the whole type
        e.sub = " ".join(_str(a.get(k)) for k in ("subType", "descriptor")).strip().lower()
        tid, pid = _int(a.get("teamId")), _int(a.get("personId"))
        e.team = tid if tid in teams else (pid if pid in teams else None)
        e.person = pid if pid is not None and pid not in teams else None
        e.possession = _int(a.get("possession"))
        if at in ("2pt", "3pt"):
            e.kind, e.value = "fga", (3 if at == "3pt" else 2)
            e.made = a.get("shotResult") == "Made"
            dist = _str(a.get("shotDistance"))
            e.distance = float(dist) if dist else None
            e.event_id = _int(a.get("actionNumber"))
            e.assist = _int(a.get("assistPersonId")) if e.made else None
            e.blocker = _int(a.get("blockPersonId")) if not e.made else None
        elif at == "freethrow":
            e.kind = "fta"
            m = _FT_OF.search(e.sub)
            e.ft_n, e.ft_of = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            e.made = a.get("shotResult") == "Made"
        elif at == "rebound":
            e.kind = "reb"
        elif at == "turnover":
            e.kind = "tov"
        elif at == "foul":
            e.kind = "foul"
            e.drawn = _int(a.get("foulDrawnPersonId"))
        elif at in ("steal", "block"):
            e.kind = at
        elif at == "substitution":
            prev = evs[-1] if evs else None
            if prev is not None and prev.kind == "sub" and prev.team == e.team \
                    and prev.period == period and prev.clock == clock and e.person:
                (prev.outs if e.sub == "out" else prev.ins).append(e.person)
                continue
            e.kind = "sub"
            if e.person:
                (e.outs if e.sub == "out" else e.ins).append(e.person)
        elif at == "jumpball":
            e.kind = "jump"
        elif at == "violation":
            e.kind = "violation"
        elif at == "period":
            e.kind = "period"
        evs.append(e)
    return evs


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

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


@dataclass
class GameAccount:
    game_id: str
    on_court: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    player_events: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    turnovers_by_type: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    seconds_on: dict = field(default_factory=lambda: defaultdict(float))
    stints: list = field(default_factory=list)        # ten-man stints (ridge rows)
    player_stints: list = field(default_factory=list)  # (player, minutes) continuous stretches
    shots: list = field(default_factory=list)          # (event_id, shooter, team, value, made, dist, stint, minutes_on)
    assists: list = field(default_factory=list)        # (assister, shooter, event_id)
    shooting_fouls: int = 0
    shooting_foul_ft_points: float = 0.0
    events_total: int = 0
    events_unresolved: int = 0
    diagnostics: dict = field(default_factory=lambda: defaultdict(int))
    examples: list = field(default_factory=list)


class _Game:
    def __init__(self, box, stints):
        self.teams = sorted({int(t) for t in box["teamId"]})
        if len(self.teams) != 2:
            raise ValueError(f"box score has {len(self.teams)} teams")
        self.other = {self.teams[0]: self.teams[1], self.teams[1]: self.teams[0]}
        self.team_of_player, self.played = {}, set()
        self.starters = defaultdict(list)
        self.names = defaultdict(lambda: defaultdict(set))   # team -> normalized name -> pids
        for row in box.itertuples(index=False):
            pid, tid = int(row.personId), int(row.teamId)
            self.team_of_player[pid] = tid
            self.names[tid][norm_name(row.familyName)].add(pid)
            # play-by-play sometimes uses another form: "J. Williams", or a given name
            # where the box score files the family name first (e.g. Yang Hansen)
            for alt in (getattr(row, "nameI", None), getattr(row, "firstName", None)):
                if alt:
                    self.names[tid][norm_name(alt)].add(pid)
            if str(row.minutes or "").strip() not in ("", "0", "0:00", "00:00"):
                self.played.add(pid)
            if str(row.position or "").strip():
                self.starters[tid].append(pid)
        self.stints = stints

    def player(self, pid):
        return pid if pid in self.team_of_player else None

    def learn_names(self, rows):
        for r in rows:
            p = self.player(_int(r.get("personId")))
            if p is None:
                continue
            for key in ("playerName", "playerNameI"):
                if r.get(key):
                    self.names[self.team_of_player[p]][norm_name(r[key])].add(p)

    def name_candidates(self, team, name):
        return {p for p in self.names[team].get(norm_name(name), set()) if p in self.played}


def _presence(g, e):
    """The player this event proves was on the floor, if any."""
    if e.kind == "sub":
        return None
    if e.kind == "foul" and "technical" in e.sub:
        return None
    if e.kind in ("fga", "fta", "reb", "tov", "foul", "steal", "block", "jump", "violation"):
        return g.player(e.person)
    return None


def _period_starters_from_rotation(g, team, period):
    if not g.stints:
        return None
    ps = period_start(period)
    on = [s.player_id for s in g.stints if s.team_id == team and s.t_in - 1 <= ps < s.t_out - 1]
    return set(on) if len(on) == 5 else None


def _infer_lineup(g, team, evs_after, known_off=(), fallback=None):
    """Lineup at a point in time: players seen acting (or being subbed out) after it,
    before any substitution brings them in. Completed from `fallback` (the last known
    lineup) only when that fills exactly the missing places."""
    seen, subbed_in = [], set(known_off)
    for e in evs_after:
        if e.team != team:
            continue
        cands = []
        if e.kind == "sub":
            for name in e.in_names:
                subbed_in |= g.name_candidates(team, name) - set(e.outs)
            subbed_in |= set(e.ins)
            cands = [g.player(p) for p in e.outs]
        else:
            cands = [_presence(g, e)]
        for p in cands:
            if p is not None and g.team_of_player[p] == team and p not in subbed_in and p not in seen:
                seen.append(p)
        if len(seen) == 5:
            return set(seen), False
    if fallback is None:
        return None, False
    fill = [p for p in fallback if p not in seen and p not in subbed_in]
    if len(seen) + len(fill) == 5:
        return set(seen) | set(fill), True
    return None, False


def account_game(game_id, evs, box, stints=None, raw_rows=None):
    """Walk one game's events: on-floor counts, seconds, stints, player events."""
    acc = GameAccount(game_id)
    diag = acc.diagnostics
    g = _Game(box, stints)
    if raw_rows is not None:
        g.learn_names(raw_rows)

    by_period = defaultdict(list)
    for e in evs:
        by_period[e.period].append(e)

    lineup = {}
    last_known = {t: None for t in g.teams}
    departed = {t: set() for t in g.teams}
    prev_end = {t: None for t in g.teams}
    entered = {}                      # player -> time he last came on the floor
    exact_entry = set()               # players whose entry time is known exactly
    state = {"last_miss_team": None, "possession": None, "stint": None,
             "pending_sf": None, "last_block": None}

    def valid(team=None):
        teams = g.teams if team is None else [team]
        return all(lineup.get(t) is not None and len(lineup[t]) == 5 for t in teams)

    def credit(team, team_field, opp_field, count=True):
        """count=False for a second field credited from the same event."""
        if count:
            acc.events_total += 1
        if not valid():
            acc.events_unresolved += count
            return False
        if team_field:
            for p in lineup[team]:
                acc.on_court[(p, team)][team_field] += 1
        if opp_field:
            for p in lineup[g.other[team]]:
                acc.on_court[(p, g.other[team])][opp_field] += 1
        return True

    def stint_count(team, key, amount=1.0):
        s = state["stint"]
        if s is not None:
            s["counts"][team][key] += amount

    def open_stint(t, period):
        close_stint(t)
        if valid():
            state["stint"] = {"game_id": game_id, "period": period, "t0": t, "t1": t,
                              "lineups": {tm: tuple(sorted(lineup[tm])) for tm in g.teams},
                              "counts": {tm: defaultdict(float) for tm in g.teams}}

    def close_stint(t):
        s = state["stint"]
        if s is not None:
            s["t1"] = t
            if s["t1"] > s["t0"] or any(s["counts"][tm] for tm in g.teams):
                acc.stints.append(s)
        state["stint"] = None

    def set_lineup(team, new, t, exact=True):
        """exact=False: the change happened at an unknown moment (a lineup lost or
        recovered), so the affected stretches have no reliable length."""
        old = lineup.get(team) or set()
        now = new or set()
        for p in old - now:
            if p in entered:
                t_in = entered.pop(p)
                if exact and p in exact_entry:
                    acc.player_stints.append((p, (t - t_in) / 600))
                exact_entry.discard(p)
        for p in now - old:
            entered[p] = t
            if exact:
                exact_entry.add(p)
        lineup[team] = new

    def resolve_incoming(team, name, pos_evs):
        named = g.name_candidates(team, name)
        cands = named - (lineup.get(team) or set())
        if len(cands) == 1:
            return next(iter(cands)), None
        if len(cands) > 1:   # same surname: the one who shows up next is the one who came in
            for e in pos_evs:
                p = g.player(e.person)
                if p in cands or any(o in cands for o in e.outs):
                    diag["subs_resolved_by_lookahead"] += 1
                    return (p if p in cands else next(o for o in e.outs if o in cands)), None
            return None, "incoming name matches several players, none seen afterwards"
        if named:
            return None, "incoming player already in tracked lineup"
        return None, "incoming name not found in box score"

    def substitute(team, e, later):
        current = lineup.get(team)
        if current is None:
            return None, "lineup already unknown"
        outs = [p for p in e.outs if g.player(p) is not None]
        ins = [p for p in e.ins if g.player(p) is not None]
        for name in e.in_names:
            pid, why = resolve_incoming(team, name, later)
            if pid is None:
                return None, why
            ins.append(pid)
        if any(p not in current for p in outs):
            return None, "outgoing player not in tracked lineup"
        return (current - set(outs)) | set(ins), None

    def recover(team, later, fallback):
        known_off = departed[team]
        fb = (fallback - known_off) if fallback else None
        new, _ = _infer_lineup(g, team, later, known_off, fb or None)
        if new:
            diag["lineups_recovered_mid_period"] += 1
        return new

    for period in sorted(by_period):
        pevs = by_period[period]
        ps = period_start(period)
        # every stretch was closed at the end of the previous period
        entered.clear()
        exact_entry.clear()
        for team in g.teams:
            departed[team] = set()
            lineup[team] = None
            if period == 1 and len(g.starters[team]) == 5:
                starters = set(g.starters[team])
            else:
                starters = _period_starters_from_rotation(g, team, period)
                if starters is None:
                    starters, completed = _infer_lineup(g, team, pevs, fallback=prev_end[team])
                    diag["period_starters_inferred"] += 1
                    diag["period_starters_completed_from_previous_period"] += completed
                if starters is None:
                    diag["period_starters_unresolved"] += 1
            set_lineup(team, starters, ps)
        state.update(pending_sf=None, last_miss_team=None, possession=None, last_block=None)
        open_stint(ps, period)

        t_prev = ps
        for k, e in enumerate(pevs):
            t = e.t
            if t > t_prev:
                for team in g.teams:
                    if valid(team):
                        for p in lineup[team]:
                            acc.seconds_on[p] += (t - t_prev) / 10
                t_prev = t
            later = pevs[k + 1:]

            changed = False
            for team in g.teams:
                if lineup.get(team) is None:
                    recovered = recover(team, pevs[k:], last_known[team])
                    if recovered is not None:
                        set_lineup(team, recovered, t, exact=False)
                        changed = True
                if valid(team):
                    last_known[team], departed[team] = lineup[team], set()
            if changed:
                open_stint(t, period)

            if e.possession in g.other:
                state["possession"] = e.possession

            if e.kind == "sub":
                team = e.team
                if team is None:
                    continue
                new, why = substitute(team, e, later)
                if new is not None and len(new) == 5:
                    set_lineup(team, new, t)
                    open_stint(t, period)
                    continue
                if why != "lineup already unknown":
                    diag["subs_unresolved"] += 1
                    diag[f"subs_unresolved: {why}"] += 1
                    if len(acc.examples) < 25:
                        acc.examples.append(f"{game_id} Q{period} {e.clock} team {team}: "
                                            f"outs={e.outs} ins={e.ins or e.in_names} -> {why}")
                departed[team].update(e.outs)
                fb = (lineup.get(team) or last_known[team] or set())
                recovered = recover(team, later, fb)
                set_lineup(team, None, t, exact=False)
                set_lineup(team, recovered, t, exact=False)
                if recovered is not None:
                    last_known[team], departed[team] = recovered, set()
                open_stint(t, period)
                continue

            team = e.team
            if team is None:
                continue
            person = g.player(e.person)

            if e.kind == "fga":
                cat = shot_category(e.value, e.distance)
                credit(team, "team_fga", "opp_fga")
                if e.value == 2:
                    credit(team, None, "opp_fg2a", count=False)
                stint_count(team, "fga")
                if e.distance is not None and e.distance < 6:
                    stint_count(team, "rim_fga")
                minutes_on = (t - entered[person]) / 600 if person in exact_entry else np.nan
                s = state["stint"]
                acc.shots.append((e.event_id, person, team, e.value, e.made, e.distance,
                                  len(acc.stints) if s is not None else None, minutes_on))
                if s is not None:
                    s["counts"][team].setdefault("shot_ids", []).append(e.event_id)
                if e.made:
                    credit(team, "team_fgm", None, count=False)
                    stint_count(team, "pts", e.value)
                    state["last_miss_team"] = None
                    state["possession"] = g.other[team]
                    assister = g.player(e.assist)
                    if assister is None and e.assist_name:
                        named = g.name_candidates(team, e.assist_name) - {person}
                        assister = next(iter(named)) if len(named) == 1 else None
                    if assister is not None:
                        acc.assists.append((assister, person, e.event_id))
                else:
                    credit(team, "team_missed_fga", "opp_missed_fga", count=False)
                    state["last_miss_team"] = team
                    state["possession"] = team
                    blocker = g.player(e.blocker)
                    state["last_block"] = None
                    if blocker is not None:
                        pe = acc.player_events[blocker]
                        pe["pbp_blocks"] += 1
                        pe[f"pbp_blocks_{cat}"] += 1
                        state["last_block"] = (blocker, g.team_of_player[blocker])
                state["pending_sf"] = None if state["pending_sf"] and state["pending_sf"]["team"] != team \
                    else state["pending_sf"]
            elif e.kind == "fta":
                credit(team, "team_fta", "opp_fta")
                stint_count(team, "fta")
                if e.made:
                    stint_count(team, "pts", 1)
                sf = state["pending_sf"]
                regular = e.ft_of > 0 and not any(w in e.sub for w in ("technical", "flagrant", "clear path"))
                if sf is not None and sf["team"] == team and regular:
                    acc.shooting_foul_ft_points += 1 if e.made else 0
                    if e.ft_n == e.ft_of:
                        state["pending_sf"] = None
                if e.made:
                    state["last_miss_team"] = None
                else:
                    state["last_miss_team"] = team
                    if is_reboundable_final_ft(e.sub):
                        credit(team, None, "opp_missed_final_ft", count=False)
            elif e.kind == "reb":
                lb = state["last_block"]
                if lb is not None:
                    if lb[1] == team:
                        acc.player_events[lb[0]]["pbp_blocks_recovered"] += 1
                    state["last_block"] = None
                if person in g.played and state["last_miss_team"] is not None:
                    if team == state["last_miss_team"]:
                        credit(team, "team_oreb", "opp_oreb")
                        stint_count(team, "oreb")
                    else:
                        credit(team, "team_dreb", "opp_dreb")
                state["last_miss_team"] = None
                state["possession"] = team
            elif e.kind == "tov":
                credit(team, "team_tov", "opp_tov")
                stint_count(team, "tov")
                if person in g.played:
                    acc.turnovers_by_type[person][e.sub] += 1
                    acc.player_events[person][f"tov_{turnover_class(e.sub)}"] += 1
                state["last_miss_team"] = None
                state["possession"] = g.other[team]
            elif e.kind == "foul" and person is not None:
                s = e.sub
                if "technical" in s:
                    continue
                if "shooting" in s:
                    acc.player_events[person]["shooting_fouls"] += 1
                    acc.shooting_fouls += 1
                    state["pending_sf"] = {"team": g.other[team]}
                elif "offensive" in s or "charge" in s:
                    drawer = g.player(e.drawn)
                    if drawer is not None:
                        acc.player_events[drawer]["offensive_fouls_drawn"] += 1
                    else:
                        diag["offensive_fouls_without_drawer"] += 1
                elif state["possession"] is not None and state["possession"] != team:
                    acc.player_events[person]["nonshooting_def_fouls"] += 1

        end = period_end(period)
        for team in g.teams:
            if valid(team):
                for p in lineup[team]:
                    acc.seconds_on[p] += (end - t_prev) / 10
            prev_end[team] = lineup.get(team)
            set_lineup(team, None, end)
        close_stint(end)
    return acc


def stint_possessions(counts):
    """Standard possession estimate for one team's counts within a stint."""
    return counts.get("fga", 0) - counts.get("oreb", 0) + counts.get("tov", 0) + 0.44 * counts.get("fta", 0)


def possessions(counts, side):
    """Standard possession estimate applied to on-court counts."""
    p = "team" if side == "off" else "opp"
    return (np.asarray(counts[f"{p}_fga"]) - np.asarray(counts[f"{p}_oreb"])
            + np.asarray(counts[f"{p}_tov"]) + 0.44 * np.asarray(counts[f"{p}_fta"]))


def _teams_of(box):
    return {int(t) for t in box["teamId"]}


def account_v3(game_id, pbp_df, box, stints=None):
    """Account a game from a PlayByPlayV3 frame (the backup source)."""
    rows = pbp_df.to_dict("records")
    return account_game(game_id, events_from_v3(rows, _teams_of(box)), box, stints, raw_rows=rows)


def account_live(game_id, actions_df, box, stints=None):
    """Account a game from cdn.nba.com liveData actions (the primary source)."""
    rows = actions_df.to_dict("records")
    return account_game(game_id, events_from_live(rows, _teams_of(box)), box, stints,
                        raw_rows=[{"personId": r.get("personId"), "playerName": r.get("playerName"),
                                   "playerNameI": r.get("playerNameI")} for r in rows])
