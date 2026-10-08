"""Print a full attribute / tendency / trait breakdown for named players from the league file.

    python pipeline/player_report.py "Cade Cunningham" "Nikola Jokic" 203507

Names match accent- and case-insensitively on any part of the full name; a number is a
player id. For every attribute it prints the rating, the Score it was ranked on, and each
component with its shrunk value and Z (and the Rule A weight for the IQ attributes), all read
from the audit tables the build writes. Nothing is computed here.
"""

import argparse
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbagm.attributes import ATTRIBUTES  # noqa: E402
from nbagm.config import LEAGUE_DB_PATH  # noqa: E402
from nbagm.tendencies import TENDENCIES  # noqa: E402
from nbagm.traits import TRAITS  # noqa: E402

GROUPS = (
    ("Rim scoring", ATTRIBUTES[0:5]), ("Shooting", ATTRIBUTES[5:8]), ("Playmaking", ATTRIBUTES[8:12]),
    ("Defense", ATTRIBUTES[12:21]), ("Physicals", ATTRIBUTES[21:27]),
)


def norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def find(con, query):
    rows = con.execute("SELECT player_id, first_name, last_name FROM players").fetchall()
    if query.isdigit():
        return [r for r in rows if r[0] == int(query)]
    q = norm(query)
    return [r for r in rows if q in norm(f"{r[1]} {r[2]}")]


def fmt(v, nd=3):
    return "-" if v is None else f"{v:.{nd}f}"


def report(con, pid):
    p = con.execute("SELECT first_name, last_name, t.abbreviation, position, position_index, height_in, "
                    "weight_lb, wingspan_in, wingspan_imputed, games_played, minutes_per_game, no_data "
                    "FROM players JOIN teams t USING (team_id) WHERE player_id = ?", (pid,)).fetchone()
    first, last, team, pos, pidx, h, w, ws, ws_imp, gp, mpg, no_data = p
    out = [f"\n{'=' * 78}\n{first} {last} ({team}, {pos} / index {pidx})  id {pid}",
           f"  {h:.0f} in, {w:.0f} lb, wingspan {ws:.1f} in{' (imputed)' if ws_imp else ''}; "
           f"{gp} GP, {mpg:.1f} MPG with this team"]
    if no_data:
        out.append("  NO DATA: every rated attribute is the placeholder 40.0 (doc 02 Population)")
    ratings = {a: (r, s, pc) for a, r, s, pc in con.execute(
        "SELECT attribute, rating, score, percentile FROM player_attributes WHERE player_id = ?", (pid,))}
    comps = {}
    for f, c, v, z in con.execute("SELECT field, component, value, z FROM components WHERE player_id = ?", (pid,)):
        comps.setdefault(f, []).append((c, v, z))
    weights = {(f, c): w for f, c, w in con.execute("SELECT field, component, weight FROM blend_weights")}
    for group, keys in GROUPS:
        out.append(f"\n  {group}")
        for a in keys:
            r, s, pc = ratings.get(a, (None, None, None))
            out.append(f"    {a:<22} {fmt(r, 1):>5}   score {fmt(s)}   pct {fmt(pc)}")
            for c, v, z in comps.get(a, []):
                wt = weights.get((a, c))
                out.append(f"        {c:<52} {fmt(v):>9}  Z {fmt(z, 2):>6}"
                           + (f"  w {wt:.3f}" if wt is not None else ""))
    out.append("\n  Tendencies (shrunk rate; raw numerator / denominator)")
    for t in TENDENCIES:
        v, n, d = con.execute("SELECT value, numerator, denominator FROM player_tendencies "
                              "WHERE player_id = ? AND tendency = ?", (pid, t.key)).fetchone()
        out.append(f"    {t.key:<36} {v:.3f}   ({fmt(n, 0)} / {fmt(d, 1)})")
    out.append("\n  Traits")
    for t in TRAITS:
        v, z, tier, name = con.execute("SELECT value, z_score, tier, tier_name FROM player_traits "
                                       "WHERE player_id = ? AND trait = ?", (pid, t)).fetchone()
        out.append(f"    {t:<14} z {z:+.2f}  tier {tier:+d}  {name or '(no trait)'}   value {fmt(v)}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("players", nargs="+", help="name fragments or player ids")
    ap.add_argument("--db", default=str(LEAGUE_DB_PATH))
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name = 'components'").fetchone():
        raise SystemExit(f"{args.db} was written by the old pipeline; run pipeline/build.py first")
    for q in args.players:
        hits = find(con, q)
        if len(hits) != 1:
            print(f"\n'{q}': {'no player' if not hits else 'several players'} matched"
                  + "".join(f"\n    {pid}  {f} {l}" for pid, f, l in hits))
            continue
        print(report(con, hits[0][0]))


if __name__ == "__main__":
    main()
