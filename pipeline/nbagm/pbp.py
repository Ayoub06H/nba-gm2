"""Per-player on-court accounting from play-by-play (playbyplayv3) and box scores.

Several doc 02/03 denominators are "... while this player was on the floor"
(team missed FGA, opponent rebounds, defensive possessions, ...). No public
endpoint publishes those directly, so they are counted here event by event.

Lineups are tracked by walking the play-by-play in order:
  * Q1 starters come from the box score (starters carry a position).
  * Later periods' starters are not logged (between-period changes are silent):
    they come from gamerotation when that response exists, otherwise from the
    first players of each team seen acting in the period before being subbed
    in, completed if needed from the previous period's closing lineup.
  * stats.nba.com logs a substitution as personId = player going out and
    description "SUB: <in> FOR <out>"; the incoming player is matched by name
    against that team's box score.
A team whose lineup can't be resolved to exactly five players has its events
skipped (counted in GameAccount.events_unresolved) instead of guessed.

Team events (team rebounds/turnovers, timeouts) carry teamId 0 and the team's
id in personId.

Possessions use the standard estimate FGA - OREB + TOV + 0.44*FTA, applied to
the on-court counts (offense: own team's events; defense: the opponent's).
"""

import re
import unicodedata
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
_SUB = re.compile(r"^SUB:\s*(.+?)\s+FOR\s+(.+?)\s*$")

# Action types whose actor is necessarily on the floor (blank = steal/block rows).
_PRESENCE_ACTIONS = {"Made Shot", "Missed Shot", "Free Throw", "Rebound", "Turnover",
                     "Jump Ball", "Heave", "Violation", ""}


def _int(x):
    """int for real ids; None for missing values (None, NaN, '', 0)."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or x == "":
        return None
    v = int(x)
    return v or None


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


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
    # (player_id, team_id) -> field -> count
    on_court: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))
    # player_id -> turnover subType -> count
    turnovers_by_type: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    seconds_on: dict = field(default_factory=lambda: defaultdict(float))
    events_total: int = 0
    events_unresolved: int = 0
    diagnostics: dict = field(default_factory=lambda: defaultdict(int))
    examples: list = field(default_factory=list)   # unresolved substitutions, for the build log


class _Game:
    def __init__(self, box, stints):
        self.teams = sorted({int(t) for t in box["teamId"]})
        if len(self.teams) != 2:
            raise ValueError(f"box score has {len(self.teams)} teams")
        self.other = {self.teams[0]: self.teams[1], self.teams[1]: self.teams[0]}
        self.team_of_player = {}
        self.played = set()
        self.starters = defaultdict(list)
        self.names = defaultdict(lambda: defaultdict(set))   # team -> normalized name -> pids
        for row in box.itertuples(index=False):
            pid, tid = int(row.personId), int(row.teamId)
            self.team_of_player[pid] = tid
            self.names[tid][norm_name(row.familyName)].add(pid)
            name_i = getattr(row, "nameI", None)
            if name_i:
                self.names[tid][norm_name(name_i)].add(pid)
            if str(row.minutes or "").strip() not in ("", "0", "0:00", "00:00"):
                self.played.add(pid)
            if str(row.position or "").strip():
                self.starters[tid].append(pid)
        self.stints = stints

    def team(self, row):
        t = _int(row["teamId"])
        if t in self.other:
            return t
        p = _int(row["personId"])
        return p if p in self.other else None

    def player(self, row):
        p = _int(row["personId"])
        return p if p in self.team_of_player else None

    def learn_names(self, rows):
        for r in rows:
            p = self.player(r)
            if p is None:
                continue
            for key in ("playerName", "playerNameI"):
                if r.get(key):
                    self.names[self.team_of_player[p]][norm_name(r[key])].add(p)

    def name_candidates(self, team, name):
        return {p for p in self.names[team].get(norm_name(name), set()) if p in self.played}


def _is_presence(row):
    if row["actionType"] in _PRESENCE_ACTIONS:
        return True
    return row["actionType"] == "Foul" and "Technical" not in str(row["subType"])


def _period_starters_from_rotation(g, team, period):
    if not g.stints:
        return None
    ps = period_start(period)
    on = [s.player_id for s in g.stints if s.team_id == team and s.t_in - 1 <= ps < s.t_out - 1]
    return set(on) if len(on) == 5 else None


def _infer_lineup(g, team, rows_after, known_on=(), known_off=(), fallback=None):
    """Lineup at a point in time: players seen acting (or being subbed out) after it,
    before any substitution brings them in. Completed from `fallback` (the last known
    lineup) only when that fills exactly the missing places."""
    seen = [p for p in known_on]
    subbed_in = set(known_off)
    for r in rows_after:
        if g.team(r) != team:
            continue
        if r["actionType"] == "Substitution":
            m = _SUB.match(str(r["description"]))
            p = g.player(r)
            if m:
                subbed_in |= g.name_candidates(team, m.group(1)) - ({p} if p else set())
        else:
            p = g.player(r) if _is_presence(r) else None
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


def _infer_period_starters(g, team, period_rows, prev_end, diag):
    lineup, completed = _infer_lineup(g, team, period_rows, fallback=prev_end)
    if completed:
        diag["period_starters_completed_from_previous_period"] += 1
    return lineup


def account_game(game_id, pbp, box, stints=None):
    """Count on-court team/opponent events and seconds for every player in one game."""
    acc = GameAccount(game_id)
    diag = acc.diagnostics
    g = _Game(box, stints)
    rows = pbp.to_dict("records")
    g.learn_names(rows)

    by_period = defaultdict(list)
    for i, r in enumerate(rows):
        by_period[int(r["period"])].append(i)

    lineup = {}
    last_known = {t: None for t in g.teams}   # most recent fully known lineup per team
    departed = {t: set() for t in g.teams}    # subbed out since then (never used to fill)
    prev_end = {t: None for t in g.teams}
    last_miss_team = None

    def valid():
        return all(lineup.get(t) is not None and len(lineup[t]) == 5 for t in g.teams)

    def credit(team, team_field, opp_field):
        acc.events_total += 1
        if not valid():
            acc.events_unresolved += 1
            return
        if team_field:
            for p in lineup[team]:
                acc.on_court[(p, team)][team_field] += 1
        if opp_field:
            for p in lineup[g.other[team]]:
                acc.on_court[(p, g.other[team])][opp_field] += 1

    def resolve_incoming(team, name, idx):
        named = g.name_candidates(team, name)
        cands = named - (lineup.get(team) or set())
        if len(cands) == 1:
            return next(iter(cands)), None
        if len(cands) > 1:   # same surname: the one who shows up next is the one who came in
            for r in rows[idx + 1:]:
                p = g.player(r)
                if p in cands and (_is_presence(r) or r["actionType"] == "Substitution"):
                    diag["subs_resolved_by_lookahead"] += 1
                    return p, None
            return None, "incoming name matches several players, none seen afterwards"
        if named:
            return None, "incoming player already in tracked lineup"
        return None, "incoming name not found in box score"

    def substitute(team, r, idx, period_idxs):
        m = _SUB.match(str(r["description"]))
        if not m:
            return None, "unparseable description"
        current = lineup.get(team)
        out = g.player(r)
        if current is not None and out not in current:
            # occasionally the ids are the other way round; fall back to the names
            by_name = g.name_candidates(team, m.group(2)) & current
            out = next(iter(by_name)) if len(by_name) == 1 else None
            if out is None:
                return None, "outgoing player not in tracked lineup"
        incoming, why = resolve_incoming(team, m.group(1), idx)
        if incoming is None:
            return None, why
        if current is None:
            return None, "lineup already unknown"
        return (current - {out}) | {incoming}, None

    def recover(team, idx, period_idxs, known_on=(), known_off=(), fallback=None):
        after = [rows[i] for i in period_idxs if i > idx]
        new, _ = _infer_lineup(g, team, after, known_on, known_off, fallback)
        if new:
            diag["lineups_recovered_mid_period"] += 1
        return new

    for period in sorted(by_period):
        idxs = by_period[period]
        period_rows = [rows[i] for i in idxs]
        for team in g.teams:
            departed[team] = set()
            if period == 1 and len(g.starters[team]) == 5:
                lineup[team] = set(g.starters[team])
                continue
            starters = _period_starters_from_rotation(g, team, period)
            if starters is None:
                starters = _infer_period_starters(g, team, period_rows, prev_end[team], diag)
                diag["period_starters_inferred"] += 1
            if starters is None:
                diag["period_starters_unresolved"] += 1
            lineup[team] = starters

        t_prev = period_start(period)
        for idx in idxs:
            r = rows[idx]
            for team in g.teams:
                if lineup.get(team) is None:
                    # rows from here on (this one included) pin down who is on the floor now
                    fb = last_known[team] - departed[team] if last_known[team] else None
                    lineup[team] = recover(team, idx - 1, idxs, known_off=departed[team], fallback=fb)
                if lineup.get(team) is not None:
                    last_known[team] = lineup[team]
                    departed[team] = set()
            t = clock_tenths(r["clock"], period)
            if t > t_prev:
                for team in g.teams:
                    if lineup.get(team) is not None and len(lineup[team]) == 5:
                        for p in lineup[team]:
                            acc.seconds_on[p] += (t - t_prev) / 10
                t_prev = t

            action = r["actionType"]
            team = g.team(r)
            person = g.player(r)

            if action == "Substitution":
                if team is None:
                    continue
                new, why = substitute(team, r, idx, idxs)
                if new is not None and len(new) == 5:
                    lineup[team] = new
                    continue
                if why != "lineup already unknown":
                    diag["subs_unresolved"] += 1
                    diag[f"subs_unresolved: {why}"] += 1
                    if len(acc.examples) < 25:
                        acc.examples.append(
                            f"{game_id} Q{period} {r['clock']} team {team}: {r['description']!r} "
                            f"-> {why}")
                # Rebuild the lineup from what happens next instead of giving up on the period.
                if person:
                    departed[team].add(person)
                fb = (lineup.get(team) or last_known[team] or set()) - departed[team]
                lineup[team] = recover(team, idx, idxs, known_off=departed[team], fallback=fb or None)
                if lineup[team] is not None:
                    last_known[team], departed[team] = lineup[team], set()
                continue

            if team is None:
                continue
            if _int(r["isFieldGoal"]) == 1:
                credit(team, "team_fga", "opp_fga")
                made = r["shotResult"] == "Made" or action == "Made Shot"
                if made:
                    last_miss_team = None
                else:
                    credit(team, "team_missed_fga", "opp_missed_fga")
                    last_miss_team = team
            elif action == "Free Throw":
                credit(team, "team_fta", "opp_fta")
                if is_made_ft(r):
                    last_miss_team = None
                else:
                    last_miss_team = team
                    if is_reboundable_final_ft(r["subType"]):
                        # credited to the defending (rebounding) side
                        credit(team, None, "opp_missed_final_ft")
            elif action == "Rebound":
                if person in g.played and last_miss_team is not None:
                    if team == last_miss_team:
                        credit(team, "team_oreb", "opp_oreb")
                    else:
                        credit(team, "team_dreb", "opp_dreb")
                last_miss_team = None
            elif action == "Turnover":
                sub = str(r["subType"] or "")
                if "No Turnover" in sub:
                    continue
                credit(team, "team_tov", "opp_tov")
                if person in g.played:
                    acc.turnovers_by_type[person][sub] += 1
                last_miss_team = None

            if person is not None and _is_presence(r) and valid() \
                    and person not in lineup[g.team_of_player[person]]:
                diag["actor_not_in_tracked_lineup"] += 1

        end = period_end(period)
        for team in g.teams:
            if lineup.get(team) is not None and len(lineup[team]) == 5:
                for p in lineup[team]:
                    acc.seconds_on[p] += (end - t_prev) / 10
            prev_end[team] = lineup.get(team)
    return acc


def possessions(counts, side):
    """Standard possession estimate applied to on-court counts."""
    p = "team" if side == "off" else "opp"
    return (np.asarray(counts[f"{p}_fga"]) - np.asarray(counts[f"{p}_oreb"])
            + np.asarray(counts[f"{p}_tov"]) + 0.44 * np.asarray(counts[f"{p}_fta"]))
