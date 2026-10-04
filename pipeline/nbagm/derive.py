"""Attribute, tendency and trait derivations (docs 02, 03, 04).

Each field is declared once in ATTRIBUTES / TENDENCIES / TRAITS with either a
derivation or the documentation gaps (pipeline/GAPS.md) that block it. Nothing
in this module looks at who a player is: every function maps real counts for
all players through the same formula.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .shrinkage import ShrinkageError, fit_beta_binomial, fit_gamma_poisson


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

def league_percentile(values, higher_is_better=True):
    """Mid-rank percentile in (0, 1) across every player in the population (ties averaged)."""
    v = pd.Series(values, dtype=float)
    ranks = (v if higher_is_better else -v).rank(method="average")
    return ((ranks - 0.5) / len(v)).to_numpy()


def safe_rate(num, den):
    num, den = np.asarray(num, dtype=float), np.asarray(den, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den, np.nan)


def trait_tier(z):
    """Doc 04's five positions: |z| >= 2 strong, 1 <= |z| < 2 mild, otherwise no trait."""
    z = np.asarray(z, dtype=float)
    tier = np.zeros(z.shape, dtype=float)
    tier[z >= 1] = 1
    tier[z >= 2] = 2
    tier[z <= -1] = -1
    tier[z <= -2] = -2
    tier[np.isnan(z)] = np.nan
    return tier


@dataclass(frozen=True)
class Prior:
    kind: str
    name: str
    family: str
    param1: float
    param2: float
    mean: float
    n_players: int


# --------------------------------------------------------------------------- #
# Tendencies (doc 03): Beta-Binomial-shrunk real rate, stored directly in [0, 1]
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TendencySpec:
    key: str
    numerator: str
    denominator: tuple   # input columns summed to form the opportunity count
    source: str
    gaps: tuple = ()     # flags implemented as written but needing confirmation


TENDENCIES = (
    TendencySpec("three_point_attempt_rate", "FG3A", ("FGA",), "3PA / FGA"),
    TendencySpec("mid_range_attempt_rate", "MID_FGA", ("FGA",), "Mid-Range zone FGA / FGA"),
    TendencySpec("rim_attempt_rate", "RIM_FGA", ("FGA",), "Restricted Area FGA / FGA"),
    TendencySpec("catch_and_shoot_vs_pull_up", "PU_FGA", ("CS_FGA", "PU_FGA"),
                 "pull-up FGA / (catch-and-shoot FGA + pull-up FGA); 1 = all pull-up"),
    TendencySpec("shot_clock_usage", "LATE_CLOCK_FGA", ("FGA",),
                 "FGA with 7-4 or 4-0 s on the shot clock / FGA"),
    TendencySpec("isolation_frequency", "SYN_Isolation_POSS", ("SYN_TOTAL_POSS",),
                 "Isolation possessions / all play-type possessions used"),
    TendencySpec("post_up_frequency", "SYN_Postup_POSS", ("SYN_TOTAL_POSS",),
                 "Post-up possessions / all play-type possessions used"),
    TendencySpec("pick_and_roll_usage", "SYN_PRBallHandler_POSS", ("SYN_TOTAL_POSS",),
                 "PnR ball-handler possessions / all play-type possessions used"),
    TendencySpec("drive_and_kick_vs_drive_to_finish", "DRIVE_PASSES", ("DRIVE_PASSES", "DRIVE_FGA"),
                 "drive passes / (drive passes + drive FGA); 1 = always kicks"),
    TendencySpec("pass_first_vs_score_first", "PASSES_MADE", ("TOUCHES",),
                 "passes made / touches; 1 = pass-first"),
    TendencySpec("foul_contact_seeking", "FTA", ("FGA",), "FTA / FGA", gaps=("F1",)),
    TendencySpec("cutting_frequency", "SYN_Cut_POSS", ("SYN_TOTAL_POSS",),
                 "Cut possessions / all play-type possessions used"),
    TendencySpec("screen_setting_willingness", "SCREEN_ASSISTS", ("OFF_POSS",),
                 "screen assists / team offensive possessions on floor"),
    TendencySpec("gamble_for_steals", "DEFLECTIONS", ("DEF_POSS",),
                 "deflections / defensive possessions on floor"),
    TendencySpec("help_defense_aggressiveness", "HELP_FGA", ("MATCHUP_FGA", "HELP_FGA"),
                 "help FGA / (matchup FGA + help FGA)"),
    TendencySpec("defensive_foul_aggression", "PF", ("DEF_POSS",),
                 "personal fouls / defensive possessions on floor", gaps=("F2",)),
    TendencySpec("offensive_rebound_crash_rate", "OREB_CHANCES", ("team_missed_fga",),
                 "offensive rebound chances / team missed FGA on floor"),
    TendencySpec("box_out_vs_leak_out", "BOX_OUTS", ("opp_fga", "opp_missed_final_ft"),
                 "box outs / (opponent FGA + opponent missed final FT) on floor; 1 = always boxes out",
                 gaps=("F3",)),
    TendencySpec("fast_break_leak_out", "SYN_Transition_POSS", ("SYN_TOTAL_POSS",),
                 "Transition possessions / all play-type possessions used"),
    TendencySpec("loose_ball_willingness", "LOOSE_BALLS", ("OFF_POSS", "DEF_POSS"),
                 "loose balls recovered / total possessions on floor"),
    TendencySpec("charge_taking_willingness", "CHARGES_DRAWN", ("DEF_POSS",),
                 "charges drawn / defensive possessions on floor"),
)


def derive_tendencies(inputs):
    """Returns (rows, priors, failures). A tendency whose real data violates the
    method's preconditions is left NULL for everyone and reported in failures,
    rather than patched."""
    rows, priors, failures = [], [], {}
    for spec in TENDENCIES:
        num = inputs[spec.numerator].to_numpy(dtype=float)
        den = sum(inputs[c].to_numpy(dtype=float) for c in spec.denominator)
        try:
            prior = fit_beta_binomial(num, den)
        except ShrinkageError as e:
            failures[spec.key] = str(e)
            value = np.full(len(num), np.nan)
        else:
            value = prior.posterior_mean(num, den)
            priors.append(Prior("tendency", spec.key, "beta", prior.alpha, prior.beta,
                                prior.mean, prior.n_players))
        rows.append(pd.DataFrame({
            "player_id": inputs.index, "tendency": spec.key, "numerator": num,
            "denominator": den, "raw_rate": safe_rate(num, den), "value": value}))
    return pd.concat(rows, ignore_index=True), priors, failures


# --------------------------------------------------------------------------- #
# Attributes (doc 02): real stat -> shrinkage -> [difficulty] -> percentile -> curve
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AttributeSpec:
    key: str
    family: str = ""                # beta | gamma ; "" when blocked before shrinkage
    higher_is_better: bool = True
    source: str = ""
    gaps: tuple = ()                # blocking gaps for the stages that are not derived
    stage: str = "blocked"          # "percentile" = derived through the percentile step


# G1 (percentile -> 0-99 curve) blocks the final rating of every attribute.
ATTRIBUTES = (
    AttributeSpec("driving_layup", gaps=("G1", "G3"),
                  source="FG% on driving layups vs expected FG% for that shot"),
    AttributeSpec("driving_dunk", "beta", True, "made / attempted shots whose shot-chart action "
                  "type is a driving dunk", gaps=("G1", "F6"), stage="percentile"),
    AttributeSpec("standing_dunk", gaps=("G1", "G6")),
    AttributeSpec("touch", gaps=("G1", "G3")),
    AttributeSpec("post_scoring", gaps=("G1", "G5")),
    AttributeSpec("three_pointer", gaps=("G1", "G3", "G4")),
    AttributeSpec("mid_range", gaps=("G1", "G3", "G4")),
    AttributeSpec("free_throw", "beta", True, "FTM / FTA", gaps=("G1",), stage="percentile"),
    AttributeSpec("ball_handle", gaps=("G1", "G7")),
    AttributeSpec("passing_accuracy", "beta", False,
                  "PASSTOV = bad-pass TOV / (potential assists + bad-pass TOV); lower is better",
                  gaps=("G1",), stage="percentile"),
    AttributeSpec("vision", gaps=("G1", "G2", "G5", "G8")),
    AttributeSpec("ball_security", "gamma", False,
                  "cTOV% = TOV per 100 / Offensive Load (Gamma-Poisson, exposure = Offensive "
                  "Load x possessions / 100); lower is better", gaps=("G1", "F7"),
                  stage="percentile"),
    AttributeSpec("shot_selection", gaps=("G1", "G9")),
    AttributeSpec("offensive_iq", gaps=("G1", "G10")),
    AttributeSpec("offensive_rebounding", "beta", True,
                  "ORB% = OREB / (team OREB + opponent DREB) on floor", gaps=("G1",),
                  stage="percentile"),
    AttributeSpec("defensive_rebounding", "beta", True,
                  "DRB% = DREB / (team DREB + opponent OREB) on floor", gaps=("G1",),
                  stage="percentile"),
    AttributeSpec("steals", "beta", True, "STL% = STL / opponent possessions on floor",
                  gaps=("G1",), stage="percentile"),
    AttributeSpec("off_ball_defense", gaps=("G1", "G11")),
    AttributeSpec("on_ball_defense", gaps=("G1", "G3", "G5")),
    AttributeSpec("post_defense", "gamma", False,
                  "opponent points / post-up possessions defended (Gamma-Poisson); lower is better",
                  gaps=("G1",), stage="percentile"),
    AttributeSpec("rim_protection", gaps=("G1", "G5")),
    AttributeSpec("defensive_iq", gaps=("G1", "G10")),
    AttributeSpec("speed", gaps=("G1", "G13")),
    AttributeSpec("acceleration", gaps=("G1", "G13")),
    AttributeSpec("lateral_quickness", gaps=("G1", "G14")),
    AttributeSpec("vertical", gaps=("G1", "G15")),
    AttributeSpec("strength", gaps=("G1", "G12")),
    AttributeSpec("stamina", gaps=("G1", "G16")),
)


def is_driving_dunk(action_type):
    a = pd.Series(action_type, dtype=str)
    return (a.str.contains("Driving", regex=False) & a.str.contains("Dunk", regex=False)).to_numpy()


def offensive_load(inputs):
    """Ben Taylor's Box Creation and Offensive Load (doc 02), per 100 on-court
    offensive possessions. Returns (offensive_load, possessions)."""
    poss = inputs["OFF_POSS"].to_numpy(dtype=float)
    per100 = {c: safe_rate(inputs[c].to_numpy(dtype=float) * 100, poss)
              for c in ("AST", "PTS", "TOV", "FG3A", "FGA", "FTA")}
    fg3_pct = np.nan_to_num(safe_rate(inputs["FG3M"], inputs["FG3A"]))
    prof = (2 / (1 + np.exp(-per100["FG3A"])) - 1) * fg3_pct
    ast, pts_tov = per100["AST"], per100["PTS"] + per100["TOV"]
    box_creation = (ast * 0.1843 + pts_tov * 0.0969 - 2.3021 * prof
                    + 0.0582 * (ast * pts_tov * prof) - 1.1942)
    load = ((ast - 0.38 * box_creation) * 0.75 + per100["FGA"] + per100["FTA"] * 0.44
            + box_creation + per100["TOV"])
    return load, poss


def attribute_counts(key, inputs, shots):
    """(successes, opportunities) for each attribute derived through shrinkage."""
    ids = inputs.index
    if key == "driving_dunk":
        dd = shots[is_driving_dunk(shots["ACTION_TYPE"])]
        g = dd.groupby(dd["PLAYER_ID"].astype(int))
        made = g["SHOT_MADE_FLAG"].sum().reindex(ids, fill_value=0)
        att = g["SHOT_MADE_FLAG"].size().reindex(ids, fill_value=0)
        return made.to_numpy(float), att.to_numpy(float)
    if key == "free_throw":
        return inputs["FTM"].to_numpy(float), inputs["FTA"].to_numpy(float)
    if key == "passing_accuracy":
        bad = inputs["BAD_PASS_TOV"].to_numpy(float)
        return bad, inputs["POTENTIAL_AST"].to_numpy(float) + bad
    if key == "ball_security":
        load, poss = offensive_load(inputs)
        exposure = np.where(np.isfinite(load) & (load > 0), load * poss / 100, 0.0)
        return inputs["TOV"].to_numpy(float), exposure
    if key == "offensive_rebounding":
        return (inputs["OREB"].to_numpy(float),
                (inputs["team_oreb"] + inputs["opp_dreb"]).to_numpy(float))
    if key == "defensive_rebounding":
        return (inputs["DREB"].to_numpy(float),
                (inputs["team_dreb"] + inputs["opp_oreb"]).to_numpy(float))
    if key == "steals":
        return inputs["STL"].to_numpy(float), inputs["DEF_POSS"].to_numpy(float)
    if key == "post_defense":
        return (inputs["SYN_D_Postup_PTS"].to_numpy(float),
                inputs["SYN_D_Postup_POSS"].to_numpy(float))
    raise KeyError(key)


def derive_attributes(inputs, shots):
    """Returns (rows, priors, failures); see derive_tendencies."""
    rows, priors, failures = [], [], {}
    n = len(inputs)
    for spec in ATTRIBUTES:
        if spec.stage != "blocked":
            s, o = attribute_counts(spec.key, inputs, shots)
            try:
                prior = (fit_beta_binomial(s, o) if spec.family == "beta"
                         else fit_gamma_poisson(s, o))
            except ShrinkageError as e:
                failures[spec.key] = str(e)
        if spec.stage == "blocked" or spec.key in failures:
            rows.append(pd.DataFrame({"player_id": inputs.index, "attribute": spec.key,
                                      **{c: np.full(n, np.nan) for c in (
                                          "successes", "opportunities", "raw_value",
                                          "shrunk_value", "percentile", "rating")}}))
            continue
        shrunk = prior.posterior_mean(s, o)
        if spec.family == "beta":
            priors.append(Prior("attribute", spec.key, "beta", prior.alpha, prior.beta,
                                prior.mean, prior.n_players))
        else:
            priors.append(Prior("attribute", spec.key, "gamma", prior.k, prior.theta,
                                prior.mean, prior.n_players))
        rows.append(pd.DataFrame({
            "player_id": inputs.index, "attribute": spec.key, "successes": s,
            "opportunities": o, "raw_value": safe_rate(s, o), "shrunk_value": shrunk,
            "percentile": league_percentile(shrunk, spec.higher_is_better),
            "rating": np.full(n, np.nan)}))   # G1: curve unspecified
    return pd.concat(rows, ignore_index=True), priors, failures


# --------------------------------------------------------------------------- #
# Traits (doc 04)
# --------------------------------------------------------------------------- #

TIER_NAMES = {
    "durability": ("Hospitalized", "Injury Prone", None, "Sturdy", "Iron Man"),
    "consistency": ("Erratic", "Inconsistent", None, "Steady", "Metronome"),
    "clutch": ("Rattled", "Shaky", None, "Clutch", "Ice in His Veins"),
    "hustle": ("Lazy", "Below Average", None, "High Motor", "Relentless"),
    "streaky": ("Even-Keeled", "Level", None, "Streaky", "Heat Check"),
}


@dataclass(frozen=True)
class TraitSpec:
    key: str
    derived: bool
    source: str = ""
    gaps: tuple = ()


TRAITS = (
    TraitSpec("durability", False, gaps=("G17",)),
    TraitSpec("consistency", False, gaps=("G2", "G18")),
    TraitSpec("clutch", False, gaps=("G19",)),
    TraitSpec("hustle", True, "equal-weight mean of league z-scores of deflections, loose balls, "
              "charges, screen assists and contested shots per on-floor exposure plus the "
              "Gamble/Loose Ball/OREB Crash/Charge-Taking tendencies", gaps=("F4",)),
    TraitSpec("streaky", True, "Wald-Wolfowitz runs test on the ordered make/miss sequence of "
              "all FGA; value = -z (fewer runs than chance = streakier)", gaps=("F5",)),
)


def runs_test_z(made_sequence):
    """Wald-Wolfowitz runs test z for a 0/1 sequence. Positive z = more runs than chance.
    With no makes or no misses the run count always equals its expectation, so z = 0."""
    x = np.asarray(made_sequence, dtype=int)
    n = len(x)
    n1 = int(x.sum())
    n2 = n - n1
    if n1 == 0 or n2 == 0:
        return 0.0
    runs = 1 + int(np.count_nonzero(x[1:] != x[:-1]))
    mu = 2.0 * n1 * n2 / n + 1
    var = (mu - 1) * (mu - 2) / (n - 1)
    if var <= 0:
        return 0.0
    return (runs - mu) / np.sqrt(var)


def streaky(shots, player_ids):
    ordered = shots.sort_values(["GAME_DATE", "GAME_ID", "GAME_EVENT_ID"])
    z = {int(pid): runs_test_z(g["SHOT_MADE_FLAG"].to_numpy())
         for pid, g in ordered.groupby("PLAYER_ID")}
    value = np.array([-z.get(int(p), 0.0) for p in player_ids])
    return value, value   # the runs-test null is the reference, so z = value


HUSTLE_RATE_COMPONENTS = (
    ("DEFLECTIONS", ("DEF_POSS",)),
    ("LOOSE_BALLS", ("OFF_POSS", "DEF_POSS")),
    ("CHARGES_DRAWN", ("DEF_POSS",)),
    ("SCREEN_ASSISTS", ("OFF_POSS",)),
    ("CONTESTED_SHOTS", ("DEF_POSS",)),
)
HUSTLE_TENDENCY_COMPONENTS = (
    "gamble_for_steals", "loose_ball_willingness", "offensive_rebound_crash_rate",
    "charge_taking_willingness",
)


def _zscore(x):
    x = np.asarray(x, dtype=float)
    ok = ~np.isnan(x)
    mu, sd = x[ok].mean(), x[ok].std()
    return (x - mu) / sd


def hustle(inputs, tendencies):
    comps = []
    for num, dens in HUSTLE_RATE_COMPONENTS:
        comps.append(_zscore(safe_rate(inputs[num], sum(inputs[d] for d in dens))))
    t = tendencies.pivot(index="player_id", columns="tendency", values="value").reindex(inputs.index)
    for key in HUSTLE_TENDENCY_COMPONENTS:
        comps.append(_zscore(t[key].to_numpy()))
    composite = np.mean(np.vstack(comps), axis=0)   # NaN if any component is undefined
    return composite, _zscore(composite)


def derive_traits(inputs, tendencies, shots):
    rows = []
    n = len(inputs)
    for spec in TRAITS:
        if spec.key == "hustle":
            value, z = hustle(inputs, tendencies)
        elif spec.key == "streaky":
            value, z = streaky(shots, inputs.index)
        else:
            value = z = np.full(n, np.nan)
        tier = trait_tier(z)
        names = TIER_NAMES[spec.key]
        tier_name = [None if np.isnan(t) else names[int(t) + 2] for t in tier]
        rows.append(pd.DataFrame({"player_id": inputs.index, "trait": spec.key, "value": value,
                                  "z_score": z, "tier": tier, "tier_name": tier_name}))
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------- #
# Measurables and depth chart (doc 11)
# --------------------------------------------------------------------------- #

def wingspans(roster, combine):
    """Combine wingspan where measured; otherwise a + b*height, fit by least squares on
    rostered players who have both a combine wingspan and a listed height (doc 11)."""
    r = roster.set_index("player_id")
    measured = combine["wingspan_in"].reindex(r.index)
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
