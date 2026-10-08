"""Print raw values from your cache so problems can be diagnosed without re-downloading.

    python pipeline/inspect_cache.py            # play-by-play format of one game
    python pipeline/inspect_cache.py data       # inputs behind the tendencies that failed
    python pipeline/inspect_cache.py live       # cdn.nba.com play-by-play, inactive lists, DNP comments
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbagm.config import RAW_CACHE_PATH  # noqa: E402
from nbagm.frames import tables  # noqa: E402
from nbagm.rawstore import RawStore  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 45)

store = RawStore(RAW_CACHE_PATH)

if len(sys.argv) > 1 and sys.argv[1] == "live":
    import json
    from collections import Counter
    row = store._conn.execute(
        "SELECT params FROM raw WHERE endpoint = 'live.playbyplay' ORDER BY params LIMIT 1").fetchone()
    params = json.loads(row[0])
    acts = store.get("live.playbyplay", params)["game"]["actions"]
    print("GAME", params["game_id"], "-", len(acts), "actions")
    print("ALL KEYS:", sorted({k for a in acts for k in a}))
    print("\nactionType / subType counts:")
    for (t, st), n in sorted(Counter((a.get("actionType"), a.get("subType")) for a in acts).items(),
                             key=lambda kv: -kv[1]):
        print(f"  {t!s:<14} {st!s:<28} {n}")
    skip = {"edited", "timeActual", "orderNumber", "xLegacy", "yLegacy", "x", "y", "side",
            "scoreHome", "scoreAway", "periodType", "teamTricode", "playerName"}
    seen = Counter()
    print("\nSAMPLE ACTIONS (2 per type):")
    for a in acts:
        t = (a.get("actionType"), a.get("subType"))
        if seen[t] < 2 and t[0] in ("substitution", "2pt", "3pt", "freethrow", "rebound", "turnover",
                                    "foul", "block", "steal", "violation", "jumpball", "period"):
            seen[t] += 1
            print({k: v for k, v in a.items() if k not in skip})
    srow = store._conn.execute(
        "SELECT params FROM raw WHERE endpoint = 'boxscoresummaryv3' ORDER BY params LIMIT 1").fetchone()
    if srow:
        sp = json.loads(srow[0])
        inactive = tables("boxscoresummaryv3", store.get("boxscoresummaryv3", sp))["InactivePlayers"]
        print("\nINACTIVE LIST", sp["game_id"], ":\n", inactive.to_string(index=False))
        box = tables("boxscoretraditionalv3", store.get("boxscoretraditionalv3", sp))["PlayerStats"]
        print("\nBOX COMMENTS:", Counter(box["comment"].fillna("")).most_common())
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == "data":
    from nbagm import plan
    from nbagm.frames import Loader
    ld = Loader(store)
    m = pd.concat([ld.frame(f"matchups_def_{t}") for t in plan.TEAM_IDS], ignore_index=True)
    print(f"SEASON MATCHUPS: {len(m)} rows; columns: {list(m.columns)}")
    print("column totals:")
    print(m.select_dtypes("number").sum().to_string())
    print("\nnon-null counts:")
    print(m.notna().sum().to_string())
    print("\nrows with the largest MATCHUP_FGA:")
    print(m.sort_values("MATCHUP_FGA", ascending=False).head(5).to_string(index=False))
    raw = store.get(ld._league["matchups_def_1610612737"].endpoint,
                    ld._league["matchups_def_1610612737"].params)
    print("\nraw headers:", raw.get("resultSets", raw.get("resultSet"))[0]["headers"]
          if isinstance(raw.get("resultSets", raw.get("resultSet")), list)
          else raw.get("resultSets", raw.get("resultSet"))["headers"])
    touches = ld.frame("pt_Possessions")[["PLAYER_ID", "PLAYER_NAME", "TOUCHES"]]
    passing = ld.frame("pt_Passing")[["PLAYER_ID", "PASSES_MADE"]]
    tp = touches.merge(passing, on="PLAYER_ID")
    print("\nPLAYERS WITH PASSES_MADE > TOUCHES:")
    print(tp[tp["PASSES_MADE"] > tp["TOUCHES"]].to_string(index=False))
    base = ld.frame("player_base_totals")
    print("\nPLAYERS WITH FTA > FGA:")
    print(base[base["FTA"] > base["FGA"]][["PLAYER_NAME", "GP", "MIN", "FGA", "FTA"]].to_string(index=False))
    sys.exit(0)

row = store._conn.execute(
    "SELECT params FROM raw WHERE endpoint = 'playbyplayv3' ORDER BY params LIMIT 1").fetchone()
params = __import__("json").loads(row[0])
payload = store.get("playbyplayv3", params)
actions = payload["game"]["actions"]
print("GAME", params["game_id"], "-", len(actions), "actions")
print("RAW ACTION KEYS:", sorted(actions[0].keys()))
subs = [a for a in actions if str(a.get("actionType", "")).lower().startswith("sub")]
print(f"\nRAW SUBSTITUTION ACTIONS ({len(subs)} total), first 4:")
for a in subs[:4]:
    print({k: v for k, v in a.items() if k not in ("videoAvailable",)})

df = tables("playbyplayv3", payload)["PlayByPlay"]
print("\nACTION TYPES:\n", df["actionType"].value_counts().to_string())
cols = ["actionNumber", "clock", "period", "teamId", "personId", "playerNameI", "actionType",
        "subType", "description", "shotResult", "isFieldGoal"]
for t in ("period", "Substitution", "Rebound", "Free Throw", "Turnover", "Jump Ball"):
    sel = df[df["actionType"] == t][cols].head(6)
    print(f"\n--- {t} ---\n{sel.to_string(index=False) if len(sel) else '(none)'}")
print("\n--- first 12 actions of period 2 ---")
print(df[df["period"] == 2][cols].head(12).to_string(index=False))

box = tables("boxscoretraditionalv3", store.get("boxscoretraditionalv3", params))["PlayerStats"]
print("\n--- box score players ---")
print(box[["personId", "teamId", "familyName", "nameI", "position", "minutes"]].to_string(index=False))
