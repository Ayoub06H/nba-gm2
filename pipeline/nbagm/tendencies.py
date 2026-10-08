"""The 20 Phase 1 tendencies of doc 03: every one an explicit count of events over an
explicit count of real opportunities, Beta-Binomial (S1) shrunk and stored in [0, 1].
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .common import safe_div
from .shrinkage import ProportionViolation

SYN_USED = "SYN_TOTAL_POSS"


@dataclass(frozen=True)
class TendencySpec:
    key: str
    numerator: tuple      # input columns summed
    denominator: tuple    # input columns summed
    source: str


TENDENCIES = (
    TendencySpec("three_point_attempt_rate", ("FG3A",), ("FGA",), "3PA / FGA"),
    TendencySpec("mid_range_attempt_rate", ("CHART_MID_FGA",), ("CHART_FGA",),
                 "SHOT_ZONE_BASIC Mid-Range FGA / FGA (ShotChartDetail)"),
    TendencySpec("rim_attempt_rate", ("CHART_RIM_FGA",), ("CHART_FGA",),
                 "FGA with SHOT_DISTANCE < 6 ft / FGA (ShotChartDetail)"),
    TendencySpec("catch_and_shoot_vs_pull_up", ("PU_FGA",), ("CS_FGA", "PU_FGA"),
                 "pull-up FGA / (catch-and-shoot + pull-up FGA); 1 = all pull-up"),
    TendencySpec("shot_clock_usage", ("LATE_CLOCK_FGA",), ("FGA",),
                 "FGA with 7 or fewer seconds on the shot clock / FGA"),
    TendencySpec("isolation_frequency", ("SYN_Isolation_POSS",), (SYN_USED,),
                 "Isolation possessions / all play-type possessions used"),
    TendencySpec("post_up_frequency", ("SYN_Postup_POSS",), (SYN_USED,),
                 "Post-up possessions / all play-type possessions used"),
    TendencySpec("pick_and_roll_usage", ("SYN_PRBallHandler_POSS",), (SYN_USED,),
                 "PnR ball-handler possessions / all play-type possessions used"),
    TendencySpec("drive_and_kick_vs_drive_to_finish", ("DRIVE_PASSES",), ("DRIVE_PASSES", "DRIVE_FGA"),
                 "drive passes / (drive passes + drive FGA); 1 = always kicks"),
    TendencySpec("pass_first_vs_score_first", ("PASSES_MADE",), ("PASSES_MADE", "FGA"),
                 "passes made / (passes made + FGA); 1 = pass-first"),
    TendencySpec("foul_contact_seeking", ("FTA",), ("FGA", "FTA"), "FTA / (FGA + FTA)"),
    TendencySpec("cutting_frequency", ("SYN_Cut_POSS",), (SYN_USED,),
                 "Cut possessions / all play-type possessions used"),
    TendencySpec("screen_setting_willingness", ("SCREEN_ASSISTS",), ("OFF_POSS",),
                 "screen assists / team offensive possessions on floor"),
    TendencySpec("gamble_for_steals", ("DEFLECTIONS",), ("DEF_POSS",),
                 "deflections / defensive possessions on floor"),
    TendencySpec("defensive_foul_aggression", ("PF",), ("DEF_POSS",),
                 "personal fouls / defensive possessions on floor"),
    TendencySpec("offensive_rebound_crash_rate", ("OREB_CHANCES",), ("team_missed_fga",),
                 "offensive rebound chances / team missed FGA on floor"),
    TendencySpec("box_out_vs_leak_out", ("DEF_BOXOUTS",), ("opp_missed_fga", "opp_missed_final_ft"),
                 "defensive box-outs / (opponent missed FGA + missed final FT) on floor; "
                 "1 = always boxes out"),
    TendencySpec("fast_break_leak_out", ("SYN_Transition_POSS",), (SYN_USED,),
                 "Transition possessions / all play-type possessions used"),
    TendencySpec("loose_ball_willingness", ("LOOSE_BALLS_RECOVERED",), ("OFF_POSS", "DEF_POSS"),
                 "loose balls recovered / total possessions on floor"),
    TendencySpec("charge_taking_willingness", ("CHARGES_DRAWN",), ("DEF_POSS",),
                 "charges drawn / defensive possessions on floor"),
)


def add_chart_counts(inputs, shots):
    """Shot-chart numerators and their matching FGA denominator, per shooter."""
    g = shots.groupby("PLAYER_ID")
    counts = pd.DataFrame({
        "CHART_FGA": g.size(),
        "CHART_MID_FGA": g["SHOT_ZONE_BASIC"].apply(lambda z: (z == "Mid-Range").sum()),
        "CHART_RIM_FGA": g["SHOT_DISTANCE"].apply(lambda d: (d < 6).sum()),
    }).astype(float)
    counts.index.name = "player_id"
    out = inputs.drop(columns=[c for c in counts.columns if c in inputs.columns]).join(counts, how="left")
    return out.fillna({c: 0.0 for c in counts.columns})


def derive_tendencies(ctx, all_ids):
    """ctx: population context (exposed rostered players). all_ids: every rostered player.
    Non-exposed players get the prior mean (doc 02 Population). Returns (rows, failures)."""
    rows, failures = [], {}
    for spec in TENDENCIES:
        num = sum(ctx.col(c) for c in spec.numerator)
        den = sum(ctx.col(c) for c in spec.denominator)
        try:
            value = ctx.s1("tendency", spec.key, num, den)
        except ProportionViolation as e:
            failures[spec.key] = ("abort", str(e))
            continue
        except Exception as e:      # noqa: BLE001 - reported per field
            failures[spec.key] = ("failed", f"{type(e).__name__}: {e}")
            continue
        prior_mean = ctx.audit.priors[-1]["mean"]
        df = pd.DataFrame({"player_id": ctx.ids, "tendency": spec.key, "numerator": num,
                           "denominator": den, "raw_rate": safe_div(num, den), "value": value})
        missing = pd.Index(all_ids).difference(ctx.ids)
        if len(missing):
            df = pd.concat([df, pd.DataFrame({
                "player_id": missing, "tendency": spec.key, "numerator": np.nan,
                "denominator": np.nan, "raw_rate": np.nan, "value": prior_mean})], ignore_index=True)
        rows.append(df)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["player_id", "tendency", "numerator", "denominator", "raw_rate", "value"])
    return out, failures
