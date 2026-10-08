"""Measurables and depth chart (doc 02 Measurables, doc 11)."""

import numpy as np
import pandas as pd


def wingspans(roster, combine):
    """Combine wingspan where measured; otherwise a + b*height, fit by least squares on
    rostered players who have both a combine wingspan and a listed height (doc 11)."""
    r = roster.set_index("player_id")
    measured = combine["wingspan_in"].reindex(r.index) if "wingspan_in" in combine else \
        pd.Series(np.nan, index=r.index)
    fit = pd.DataFrame({"h": r["height_in"], "w": measured}).dropna()
    if len(fit) < 2:
        raise ValueError("fewer than two players with both height and combine wingspan")
    b, a = np.polyfit(fit["h"].to_numpy(), fit["w"].to_numpy(), 1)
    imputed = measured.isna()
    wingspan = measured.where(~imputed, a + b * r["height_in"])
    return wingspan, imputed, (a, b, len(fit))


def depth_chart(roster, team_usage):
    """Starters = top five by games started for the team; everyone else by minutes per game."""
    u = roster[["player_id", "team_id"]].merge(team_usage, on=["player_id", "team_id"], how="left")
    u = u.fillna({"games_played": 0, "games_started": 0, "minutes": 0.0})
    u["minutes_per_game"] = np.where(u["games_played"] > 0, u["minutes"] / u["games_played"].clip(lower=1), 0.0)
    ranked = []
    for _team, g in u.groupby("team_id"):
        g = g.sort_values(["games_started", "minutes_per_game", "player_id"],
                          ascending=[False, False, True])
        starters = g.head(5)
        bench = g.iloc[5:].sort_values(["minutes_per_game", "games_started", "player_id"],
                                       ascending=[False, False, True])
        ordered = pd.concat([starters, bench])
        ranked.append(ordered.assign(depth_rank=np.arange(1, len(ordered) + 1)))
    return pd.concat(ranked, ignore_index=True)
