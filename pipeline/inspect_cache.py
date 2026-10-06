"""Print how stats.nba.com formats play-by-play in your cache (for building the lineup parser).

    python pipeline/inspect_cache.py
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
