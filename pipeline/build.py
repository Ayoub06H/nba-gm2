"""Step 2 (offline): derive every attribute/tendency/trait and write the league SQLite file.

Reads only the local raw cache written by gather.py; no network access.

    python pipeline/build.py
"""

import argparse
import datetime as dt
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbagm import derive  # noqa: E402
from nbagm.config import LEAGUE_DB_PATH, RAW_CACHE_PATH, SCHEMA_PATH, SEASON, SEASON_TYPE  # noqa: E402
from nbagm.frames import Loader  # noqa: E402
from nbagm.league import assemble  # noqa: E402
from nbagm.rawstore import RawStore  # noqa: E402

# Unresolved on-court events above this share mean the lineup reconstruction is
# broken, not just hitting rare edge cases, so the build refuses to continue.
MAX_UNRESOLVED_EVENT_SHARE = 0.01


def _none_if_nan(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def _rows(df, cols):
    return [tuple(_none_if_nan(v) for v in row) for row in df[cols].itertuples(index=False)]


def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def derivation_status(failures):
    """failures: {(kind, key): message} for fields whose real data violated the
    method's preconditions; they are written as NULL and marked failed."""
    rows = []
    for a in derive.ATTRIBUTES:
        status = "partial" if a.stage == "percentile" else "blocked"
        note = (f"derived through league percentile: {a.source}; final 0-99 rating blocked"
                if a.stage == "percentile" else "")
        if ("attribute", a.key) in failures:
            status, note = "failed", failures[("attribute", a.key)]
        rows.append(("attribute", a.key, status, ",".join(a.gaps), note))
    for t in derive.TENDENCIES:
        status, note = "derived", t.source
        if ("tendency", t.key) in failures:
            status, note = "failed", f"{t.source}: {failures[('tendency', t.key)]}"
        rows.append(("tendency", t.key, status, ",".join(t.gaps), note))
    for t in derive.TRAITS:
        rows.append(("trait", t.key, "derived" if t.derived else "blocked", ",".join(t.gaps),
                     t.source))
    rows.append(("measurable", "height_in", "derived", "", "listed height, commonteamroster"))
    rows.append(("measurable", "weight_lb", "derived", "", "listed weight, commonteamroster"))
    rows.append(("measurable", "wingspan_in", "derived", "",
                 "draft combine; otherwise a + b*height fit on rostered players with both"))
    rows.append(("player_field", "position", "blocked", "G20", ""))
    rows.append(("player_field", "contract", "blocked", "G21", ""))
    rows.append(("player_field", "depth_rank", "derived", "",
                 "top 5 by games started for the team, then minutes per game"))
    return rows


def build(cache_path, out_path):
    store = RawStore(cache_path)
    loader = Loader(store)
    print("assembling raw inputs (play-by-play accounting takes a few minutes)...", flush=True)
    lg = assemble(loader)

    share = lg.pbp_events_unresolved / max(lg.pbp_events_total, 1)
    print(f"on-court events: {lg.pbp_events_total:,}, lineup unresolved: "
          f"{lg.pbp_events_unresolved:,} ({share:.3%})")
    d = lg.pbp_diagnostics
    n_pg = max(d.get("player_games", 0), 1)
    print(f"lineup check vs box-score minutes: mean error "
          f"{d.get('minutes_abs_error_sum', 0) / n_pg:.2f} min per player-game; "
          f"{int(d.get('player_games_off_by_over_1_min', 0))} of {int(n_pg)} player-games off by > 1 min")
    for k in sorted(d):
        if k not in ("player_games", "minutes_abs_error_sum", "player_games_off_by_over_1_min"):
            print(f"  {k}: {int(d[k])}")
    if lg.pbp_examples:
        log = Path(cache_path).parent / "lineup_diagnostics.txt"
        log.write_text("\n".join(lg.pbp_examples), encoding="utf-8")
        print(f"  sample unresolved substitutions ({len(lg.pbp_examples)} written to {log}):")
        for e in lg.pbp_examples[:12]:
            print(f"    {e}")
    if share > MAX_UNRESOLVED_EVENT_SHARE:
        raise SystemExit("lineup reconstruction failed on too many events; aborting "
                         "(send the lines above)")

    # Population: everyone who played a 2025-26 regular-season game plus every
    # rostered player. Priors are fit on players with opportunities; everyone
    # in the population receives a value.
    population = lg.inputs.index.union(pd.Index(lg.roster["player_id"])).sort_values()
    inputs = lg.inputs.reindex(population, fill_value=0.0)

    tendencies, t_priors, t_fail = derive.derive_tendencies(inputs)
    attributes, a_priors, a_fail = derive.derive_attributes(inputs, lg.shots)
    failures = {**{("tendency", k): v for k, v in t_fail.items()},
                **{("attribute", k): v for k, v in a_fail.items()}}
    for (kind, key), msg in sorted(failures.items()):
        print(f"FAILED {kind} {key}: {msg}")
    traits = derive.derive_traits(inputs, tendencies, lg.shots)

    wingspan, imputed, (a, b, n_fit) = derive.wingspans(lg.roster, lg.combine)
    print(f"wingspan imputation: wingspan = {a:.3f} + {b:.4f} * height (fit on {n_fit} players); "
          f"{int(imputed.sum())} imputed")
    depth = derive.depth_chart(lg.roster, lg.team_usage)

    roster = lg.roster.merge(depth[["player_id", "games_played", "games_started",
                                    "minutes_per_game", "depth_rank"]], on="player_id")
    roster["wingspan_in"] = roster["player_id"].map(wingspan)
    roster["wingspan_imputed"] = roster["player_id"].map(imputed).astype(int)
    first_last = roster.apply(
        lambda r: lg.names.get(r["player_id"], tuple((r["display_name"].split(" ", 1) + [""])[:2])),
        axis=1)
    roster["first_name"] = [fl[0] for fl in first_last]
    roster["last_name"] = [fl[1] for fl in first_last]
    roster["position"] = None   # G20

    rostered = set(roster["player_id"])
    attributes = attributes[attributes["player_id"].isin(rostered)]
    tendencies = tendencies[tendencies["player_id"].isin(rostered)]
    traits = traits[traits["player_id"].isin(rostered)]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(str(tmp))
    con.executescript(Path(SCHEMA_PATH).read_text())
    meta = {
        "season": SEASON, "season_type": SEASON_TYPE,
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pipeline_git_sha": git_sha(),
        "population_size": str(len(population)),
        "rostered_players": str(len(roster)),
        "pbp_events": str(lg.pbp_events_total),
        "pbp_events_unresolved": str(lg.pbp_events_unresolved),
        "lineup_minutes_mean_abs_error": f"{lg.pbp_diagnostics.get('minutes_abs_error_sum', 0) / max(lg.pbp_diagnostics.get('player_games', 0), 1):.4f}",
        "wingspan_fit": f"a={a!r};b={b!r};n={n_fit}",
    }
    con.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    con.executemany("INSERT INTO teams VALUES (?, ?, ?, ?)",
                    _rows(lg.teams, ["team_id", "abbreviation", "city", "name"]))
    pcols = ["player_id", "team_id", "first_name", "last_name", "jersey", "listed_position",
             "position", "birth_date", "experience", "height_in", "weight_lb", "wingspan_in",
             "wingspan_imputed", "games_played", "games_started", "minutes_per_game", "depth_rank"]
    con.executemany(f"INSERT INTO players ({','.join(pcols)}) VALUES ({','.join('?' * len(pcols))})",
                    _rows(roster, pcols))
    con.executemany("INSERT INTO player_attributes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    _rows(attributes, ["player_id", "attribute", "successes", "opportunities",
                                       "raw_value", "shrunk_value", "percentile", "rating"]))
    con.executemany("INSERT INTO player_tendencies VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(tendencies, ["player_id", "tendency", "numerator", "denominator",
                                       "raw_rate", "value"]))
    con.executemany("INSERT INTO player_traits VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(traits, ["player_id", "trait", "value", "z_score", "tier", "tier_name"]))
    con.executemany("INSERT INTO derivation_status VALUES (?, ?, ?, ?, ?)", derivation_status(failures))
    con.executemany("INSERT INTO priors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [tuple(_none_if_nan(v) if not (isinstance(v, float) and np.isinf(v)) else None
                           for v in (p.kind, p.name, p.family, p.param1, p.param2, p.mean,
                                     p.n_players))
                     for p in t_priors + a_priors])
    con.executemany("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(lg.games, ["game_id", "game_date", "home_team_id", "away_team_id",
                                     "home_points", "away_points"]))
    con.executemany("INSERT INTO team_season_stats VALUES (?, ?, ?)",
                    _rows(lg.team_season_stats, ["team_id", "stat", "value"]))
    con.commit()
    con.close()
    tmp.replace(out_path)
    store.close()
    report(out_path)


def report(path):
    con = sqlite3.connect(str(path))
    n = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    teams = con.execute("SELECT COUNT(DISTINCT team_id) FROM players").fetchone()[0]
    print(f"\nwrote {path}: {n} players on {teams} teams, "
          f"{con.execute('SELECT COUNT(*) FROM games').fetchone()[0]} games")
    for kind, table, col, val in (("attribute", "player_attributes", "attribute", "rating"),
                                  ("tendency", "player_tendencies", "tendency", "value"),
                                  ("trait", "player_traits", "trait", "tier")):
        rows = con.execute(f"SELECT {col}, SUM({val} IS NOT NULL) FROM {table} GROUP BY {col} "
                           f"ORDER BY {col}").fetchall()
        complete = sum(1 for _, k in rows if k == n)
        print(f"{kind} fields complete for every player: {complete}/{len(rows)}")
    blocked = con.execute("SELECT kind, name, status, gap_ids FROM derivation_status "
                          "WHERE status != 'derived' ORDER BY kind, name").fetchall()
    if blocked:
        print("\nnot yet derivable (see pipeline/GAPS.md):")
        for kind, name, status, gaps in blocked:
            print(f"  {kind:<12} {name:<36} {status:<8} {gaps}")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default=str(RAW_CACHE_PATH))
    ap.add_argument("--out", default=str(LEAGUE_DB_PATH))
    args = ap.parse_args()
    build(args.cache, args.out)


if __name__ == "__main__":
    main()
