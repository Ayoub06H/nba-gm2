"""Step 2 (offline): derive every attribute/tendency/trait and write the league SQLite file.

Reads only the local raw cache written by gather.py; no network access.

    python pipeline/build.py                     # writes data/league_2025_26.sqlite
    python pipeline/build.py --allow-incomplete  # also writes it when some field failed

A field that cannot be derived exactly as the docs define it (for example an S1
statistic whose numerator exceeds its denominator for some player) is never
patched: the build lists every such field and stops without writing the league
file, so the definition can be fixed in the docs.
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

from nbagm.attributes import ATTRIBUTES, derive_attributes  # noqa: E402
from nbagm.common import Audit, Ctx  # noqa: E402
from nbagm.config import LEAGUE_DB_PATH, RAW_CACHE_PATH, SCHEMA_PATH, SEASON, SEASON_TYPE  # noqa: E402
from nbagm.frames import Loader  # noqa: E402
from nbagm.league import assemble  # noqa: E402
from nbagm.measurables import depth_chart, wingspans  # noqa: E402
from nbagm.rawstore import RawStore  # noqa: E402
from nbagm.tendencies import TENDENCIES, add_chart_counts, derive_tendencies  # noqa: E402
from nbagm.traits import TRAITS, derive_traits  # noqa: E402

# Unresolved on-court events above this share mean the lineup reconstruction is
# broken, not just hitting rare edge cases, so the build refuses to continue.
MAX_UNRESOLVED_EVENT_SHARE = 0.01


class BuildFailed(SystemExit):
    pass


def _none_if_nan(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)) and not np.isfinite(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return int(v)
    return v


def _rows(df, cols):
    return [tuple(_none_if_nan(v) for v in row) for row in df[cols].itertuples(index=False)]


def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def print_lineup_diagnostics(lg, cache_path):
    share = lg.pbp_events_unresolved / max(lg.pbp_events_total, 1)
    print(f"on-court events: {lg.pbp_events_total:,}, lineup unresolved: "
          f"{lg.pbp_events_unresolved:,} ({share:.3%})")
    d = lg.pbp_diagnostics
    n_pg = max(d.get("player_games", 0), 1)
    print(f"lineup check vs box-score minutes: mean error "
          f"{d.get('minutes_abs_error_sum', 0) / n_pg:.4f} min per player-game; "
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
        raise BuildFailed("lineup reconstruction failed on too many events; aborting "
                          "(send the lines above)")
    return share


def population(lg, roster):
    """Doc 02: rostered players who logged at least one team possession on the floor.
    Exposure on only one side of the ball cannot happen in a real game; if the
    possession estimate says otherwise the player is reported instead of guessed."""
    inp = lg.inputs.reindex(roster["player_id"], fill_value=0.0)
    off, de = inp["OFF_POSS"] > 0, inp["DEF_POSS"] > 0
    one_sided = inp.index[off ^ de].tolist()
    return inp.index[off & de], one_sided


def build(cache_path, out_path, allow_incomplete=False):
    store = RawStore(cache_path)
    loader = Loader(store)
    print("assembling raw inputs (play-by-play accounting takes a few minutes)...", flush=True)
    lg = assemble(loader)
    share = print_lineup_diagnostics(lg, cache_path)

    print("\ndata checks (doc 02 checklist):")
    for name, ok, detail in lg.checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
    print("turnover types seen in play-by-play (doc 02 taxonomy):")
    for row in lg.turnover_types.itertuples(index=False):
        print(f"  {row.type!r:<40} {row.count:>7}  -> {row._2}")

    # Measurables (doc 02, doc 11)
    roster = lg.roster.copy()
    wingspan, imputed, (a, b, n_fit) = wingspans(roster, lg.combine)
    roster["wingspan_in"] = roster["player_id"].map(wingspan)
    roster["wingspan_imputed"] = roster["player_id"].map(imputed).astype(int)
    lg.roster = roster
    print(f"\nwingspan imputation: wingspan = {a:.3f} + {b:.4f} * height (fit on {n_fit} players); "
          f"{int(imputed.sum())} imputed")

    lg.inputs = add_chart_counts(lg.inputs, lg.shots)
    exposed, one_sided = population(lg, roster)
    all_ids = pd.Index(roster["player_id"]).sort_values()
    print(f"population: {len(exposed)} rostered players with exposure, "
          f"{len(all_ids) - len(exposed)} without (placeholder ratings)")

    audit = Audit()
    ctx = Ctx(lg.inputs, exposed.sort_values(), audit)
    failures = {}
    if one_sided:
        failures[("population", "exposure")] = (
            "failed", f"possession estimate positive on one side of the ball only for {one_sided}")

    tendencies, t_fail = derive_tendencies(ctx, all_ids)
    attributes, a_fail, builder = derive_attributes(ctx, lg, all_ids)
    traits, tr_fail = derive_traits(ctx, lg, builder, tendencies, all_ids)
    failures.update({("tendency", k): v for k, v in t_fail.items()})
    failures.update({("attribute", k): v for k, v in a_fail.items()})
    failures.update({("trait", k): v for k, v in tr_fail.items()})

    report_path = Path(cache_path).parent / "build_report.txt"
    if failures:
        lines = [f"{status.upper():<6} {kind} {key}: {msg}"
                 for (kind, key), (status, msg) in sorted(failures.items())]
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\nfields that could not be derived as the docs define them:")
        for line in lines:
            print("  " + line)
        print(f"(also written to {report_path})")
        if not allow_incomplete:
            store.close()
            raise BuildFailed("build stopped: nothing was written to the league file. Each line above "
                              "names the field and the reason; send them over.")

    depth = depth_chart(roster, lg.team_usage)
    roster = roster.merge(depth[["player_id", "games_played", "games_started", "minutes_per_game",
                                 "depth_rank"]], on="player_id")
    first_last = roster.apply(
        lambda r: lg.names.get(r["player_id"], tuple((r["display_name"].split(" ", 1) + [""])[:2])),
        axis=1)
    roster["first_name"] = [fl[0] for fl in first_last]
    roster["last_name"] = [fl[1] for fl in first_last]
    roster["no_data"] = (~roster["player_id"].isin(exposed)).astype(int)
    roster["placeholder_rating"] = roster["no_data"]

    write_db(out_path, lg, roster, attributes, tendencies, traits, audit, failures, share,
             (a, b, n_fit), len(exposed))
    store.close()
    report(out_path)


def write_db(out_path, lg, roster, attributes, tendencies, traits, audit, failures, share,
             wing_fit, n_exposed):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(str(tmp))
    con.executescript(Path(SCHEMA_PATH).read_text())
    d = lg.pbp_diagnostics
    a, b, n_fit = wing_fit
    meta = {
        "season": SEASON, "season_type": SEASON_TYPE,
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pipeline_git_sha": git_sha(),
        "rostered_players": str(len(roster)),
        "players_with_exposure": str(n_exposed),
        "pbp_events": str(lg.pbp_events_total),
        "pbp_events_unresolved": str(lg.pbp_events_unresolved),
        "pbp_unresolved_share": f"{share:.6f}",
        "pbp_games_live": str(int(d.get("games_pbp_live", 0))),
        "pbp_games_v3": str(int(d.get("games_pbp_v3", 0))),
        "lineup_minutes_mean_abs_error":
            f"{d.get('minutes_abs_error_sum', 0) / max(d.get('player_games', 0), 1):.4f}",
        "wingspan_fit": f"a={float(a):.6f};b={float(b):.6f};n={n_fit}",
        "placeholder_rating": "40.0",
        "complete": "0" if failures else "1",
    }
    con.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    con.executemany("INSERT INTO teams VALUES (?, ?, ?, ?)",
                    _rows(lg.teams, ["team_id", "abbreviation", "city", "name"]))
    pcols = ["player_id", "team_id", "first_name", "last_name", "jersey", "position", "position_index",
             "birth_date", "experience", "age", "height_in", "weight_lb", "wingspan_in",
             "wingspan_imputed", "games_played", "games_started", "minutes_per_game", "depth_rank",
             "no_data", "placeholder_rating"]
    con.executemany(f"INSERT INTO players ({','.join(pcols)}) VALUES ({','.join('?' * len(pcols))})",
                    _rows(roster, pcols))
    con.executemany("INSERT INTO player_attributes VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(attributes, ["player_id", "attribute", "score", "percentile", "rating",
                                       "placeholder"]))
    con.executemany("INSERT INTO player_tendencies VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(tendencies, ["player_id", "tendency", "numerator", "denominator",
                                       "raw_rate", "value"]))
    con.executemany("INSERT INTO player_traits VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(traits, ["player_id", "trait", "value", "z_score", "tier", "tier_name"]))
    status = []
    for kind, keys in (("attribute", ATTRIBUTES), ("tendency", [t.key for t in TENDENCIES]),
                       ("trait", TRAITS)):
        for k in keys:
            if (kind, k) in failures:
                st, msg = failures[(kind, k)]
                status.append((kind, k, st, msg))
            else:
                status.append((kind, k, "derived", ""))
    status += [("measurable", "height_in", "derived", "listed height, commonteamroster (playerindex fallback)"),
               ("measurable", "weight_lb", "derived", "listed weight, commonteamroster (playerindex fallback)"),
               ("measurable", "wingspan_in", "derived",
                "draft combine; otherwise a + b*height fit on rostered players with both"),
               ("player_field", "position", "derived", "published label, commonteamroster"),
               ("player_field", "contract", "empty", "nullable; no real source named (doc 11)"),
               ("player_field", "depth_rank", "derived",
                "top 5 by games started for the team, then minutes per game")]
    con.executemany("INSERT INTO derivation_status VALUES (?, ?, ?, ?)", status)
    con.executemany("INSERT INTO priors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [tuple(_none_if_nan(p[k]) for k in ("kind", "name", "family", "param1", "param2",
                                                        "mean", "n_players"))
                     for p in {(p["kind"], p["name"]): p for p in audit.priors}.values()])
    if audit.components:
        comp = pd.concat(audit.components, ignore_index=True)
        comp = comp.drop_duplicates(["player_id", "field", "component"], keep="last")
        con.executemany("INSERT INTO components VALUES (?, ?, ?, ?, ?)",
                        _rows(comp, ["player_id", "field", "component", "value", "z"]))
    con.executemany("INSERT INTO blend_weights VALUES (?, ?, ?)", audit.weights)
    con.executemany("INSERT OR REPLACE INTO model_parameters VALUES (?, ?, ?)",
                    [(m, k, _none_if_nan(float(v))) for m, k, v in audit.models])
    con.executemany("INSERT INTO build_notes VALUES (?, ?)", audit.notes)
    con.executemany("INSERT INTO data_checks VALUES (?, ?, ?)",
                    [(n, int(bool(ok)), str(det)) for n, ok, det in lg.checks])
    con.executemany("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)",
                    _rows(lg.games, ["game_id", "game_date", "home_team_id", "away_team_id",
                                     "home_points", "away_points"]))
    con.executemany("INSERT INTO team_season_stats VALUES (?, ?, ?)",
                    _rows(lg.team_season_stats, ["team_id", "stat", "value"]))
    con.commit()
    con.close()
    tmp.replace(out_path)


def report(path):
    con = sqlite3.connect(str(path))
    n = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    teams = con.execute("SELECT COUNT(DISTINCT team_id) FROM players").fetchone()[0]
    nd = con.execute("SELECT SUM(no_data) FROM players").fetchone()[0]
    print(f"\nwrote {path}: {n} players on {teams} teams ({nd} with no data -> placeholder 40.0), "
          f"{con.execute('SELECT COUNT(*) FROM games').fetchone()[0]} games")
    for kind, table, col, val, expected in (
            ("attribute", "player_attributes", "attribute", "rating", len(ATTRIBUTES)),
            ("tendency", "player_tendencies", "tendency", "value", len(TENDENCIES)),
            ("trait", "player_traits", "trait", "tier", len(TRAITS))):
        rows = con.execute(f"SELECT {col}, SUM({val} IS NOT NULL) FROM {table} GROUP BY {col}").fetchall()
        complete = sum(1 for _, k in rows if k == n)
        print(f"{kind} fields complete for every player: {complete}/{expected}")
    for field, note in con.execute("SELECT field, note FROM build_notes"):
        print(f"  note: {field}: {note}")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=str(RAW_CACHE_PATH))
    ap.add_argument("--out", default=str(LEAGUE_DB_PATH))
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="write the league file even if some fields failed (marked in "
                         "derivation_status and meta.complete = 0)")
    args = ap.parse_args()
    build(args.cache, args.out, args.allow_incomplete)


if __name__ == "__main__":
    main()
