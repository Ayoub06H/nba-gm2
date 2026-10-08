"""The five traits of doc 04: each player's shrunk real value, converted to standard
deviations from the population (from his peer cluster for Consistency; from the
runs-test null for Streaky), then read into five tiers.
"""

import numpy as np
import pandas as pd

from . import models
from .common import Z, DerivationError, safe_div, zstd
from .shrinkage import fit_scaled_inv_chi2

TRAITS = ("durability", "consistency", "clutch", "hustle", "streaky")
TIER_NAMES = {
    "durability": ("Hospitalized", "Injury Prone", None, "Sturdy", "Iron Man"),
    "consistency": ("Erratic", "Inconsistent", None, "Steady", "Metronome"),
    "clutch": ("Rattled", "Shaky", None, "Clutch", "Ice in His Veins"),
    "hustle": ("Lazy", "Below Average", None, "High Motor", "Relentless"),
    "streaky": ("Even-Keeled", "Level", None, "Streaky", "Heat Check"),
}
GMM_K = range(2, 13)


def tier(z):
    """2+ SD below: -2; 1-2 below: -1; within 1 SD: 0; 1-2 above: 1; 2+ above: 2."""
    z = np.asarray(z, float)
    t = np.zeros(z.shape, dtype=int)
    t[z >= 1] = 1
    t[z >= 2] = 2
    t[z <= -1] = -1
    t[z <= -2] = -2
    return t


def runs_test_z(made):
    """Wald-Wolfowitz: z_runs = (R - mu)/sigma; 0 when there are no makes or no misses.
    With one make and one miss sigma = 0 and R = mu always, so z is 0 as well."""
    made = np.asarray(made, dtype=int)
    n1, n2 = int(made.sum()), int(len(made) - made.sum())
    if n1 == 0 or n2 == 0:
        return 0.0
    runs = 1 + int(np.count_nonzero(np.diff(made)))
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = (mu - 1) * (mu - 2) / (n1 + n2 - 1)
    if var <= 0:
        return 0.0
    return (runs - mu) / np.sqrt(var)


class TraitBuilder:
    def __init__(self, ctx, lg, attr_builder, tendencies):
        self.c, self.lg, self.ab = ctx, lg, attr_builder
        self.tend = tendencies.pivot(index="player_id", columns="tendency", values="value")

    def durability(self):
        d = self.lg.durability
        missed = self.c.series(d["games_missed"])
        games = self.c.series(d["roster_games"])
        rate = self.c.s1("trait", "durability: games missed / roster games", missed, games)
        self.c.log("trait:durability", "games missed rate*", rate)
        return rate, -zstd(rate)          # higher rate is worse

    def cluster_features(self):
        c, ab = self.c, self.ab
        tf = lambda k: c.series(self.tend[k], fill=np.nan)          # noqa: E731
        ast_pct = c.s1("trait", "AST% (teammates' FGM on floor)", c.col("AST"),
                       c.col("team_fgm") - c.col("FGM"))
        reb_all = c.col("team_oreb") + c.col("team_dreb") + c.col("opp_oreb") + c.col("opp_dreb")
        trb_pct = c.s1("trait", "TRB% (all rebounds on floor)", c.col("OREB") + c.col("DREB"), reb_all)
        feats = {
            "height": ab.roster["height_in"].to_numpy(float),
            "position index": ab.roster["position_index"].to_numpy(float),
            "Offensive Load per100*": ab.ol_star,
            "3PA rate*": tf("three_point_attempt_rate"),
            "rim-attempt rate*": tf("rim_attempt_rate"),
            "AST%*": ast_pct, "TRB%*": trb_pct, "BLK%*": ab.blk_pct, "STL%*": ab.stl_pct,
        }
        X = np.column_stack(list(feats.values()))
        if np.any(~np.isfinite(X)):
            raise DerivationError("Consistency clusters: a feature is undefined for some players")
        return (X - X.mean(axis=0)) / np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0)

    def consistency(self):
        from sklearn.mixture import GaussianMixture
        c = self.c
        X = self.cluster_features()
        fits = []
        for k in GMM_K:
            if k >= len(X):
                break
            g = GaussianMixture(n_components=k, covariance_type="full", random_state=0).fit(X)
            fits.append((g.bic(X), k, g))
        bic, k, gmm = min(fits, key=lambda f: f[0])
        c.audit.models.append(("Consistency GMM", "k (lowest BIC)", k))
        for b, kk, _ in fits:
            c.audit.models.append(("Consistency GMM", f"BIC[k={kk}]", float(b)))
        cluster = gmm.predict(X)

        gl = self.lg.game_logs
        gl = gl[gl["MIN"] >= 10].copy()
        gl["gs"] = (gl["PTS"] + 0.4 * gl["FGM"] - 0.7 * gl["FGA"] - 0.4 * (gl["FTA"] - gl["FTM"])
                    + 0.7 * gl["OREB"] + 0.3 * gl["DREB"] + gl["STL"] + 0.7 * gl["AST"]
                    + 0.7 * gl["BLK"] - 0.4 * gl["PF"] - gl["TOV"]) / gl["MIN"]
        g = gl.groupby("player_id")["gs"].agg(["var", "size"])
        s2_ = c.series(g["var"].fillna(0.0))
        n = c.series(g["size"])

        value = np.full(len(c.ids), np.nan)
        z = np.full(len(c.ids), np.nan)
        for k_ in np.unique(cluster):
            m = cluster == k_
            prior = fit_scaled_inv_chi2(s2_[m], n[m])
            c.audit.priors.append(dict(kind="trait", name=f"consistency cluster {k_}",
                                       family="scaled_inv_chi2",
                                       param1=float(prior.nu0) if np.isfinite(prior.nu0) else None,
                                       param2=float(prior.s0_sq), mean=float(prior.s0_sq),
                                       n_players=prior.n_players))
            v = -np.log(prior.shrink(s2_[m], n[m]))
            value[m] = v
            z[m] = zstd(v)
        c.log("trait:consistency", "cluster", cluster.astype(float))
        c.log("trait:consistency", "-ln s*^2", value, z)
        return value, z

    def clutch(self):
        c = self.c
        gl = self.lg.game_logs
        tsa_g = gl["FGA"] + 0.44 * gl["FTA"]
        mu = gl["PTS"].sum() / tsa_g.sum()
        sigma2 = ((gl["PTS"] - mu * tsa_g) ** 2).sum() / tsa_g.sum()
        c.audit.models.append(("Clutch", "league PPTSA mu", float(mu)))
        c.audit.models.append(("Clutch", "per-attempt variance sigma^2", float(sigma2)))
        cl_tsa = c.col("CLUTCH_FGA") + 0.44 * c.col("CLUTCH_FTA")
        all_tsa = c.col("FGA") + 0.44 * c.col("FTA")
        nc_tsa = all_tsa - cl_tsa
        nc_pts = c.col("PTS") - c.col("CLUTCH_PTS")
        ok = (cl_tsa > 0) & (nc_tsa > 0)
        d = np.where(ok, safe_div(c.col("CLUTCH_PTS"), cl_tsa) - safe_div(nc_pts, nc_tsa), np.nan)
        s2_ = np.where(ok, sigma2 * (safe_div(1.0, cl_tsa) + safe_div(1.0, nc_tsa)), np.nan)
        out, _ = c.s3("trait", "clutch PPTSA delta", d, s2_, prior_mean=None)
        z = zstd(out)
        c.log("trait:clutch", "PPTSA delta*", out, z)
        return out, z

    def hustle(self):
        c, ab = self.c, self.ab
        comps = {
            "deflections per100": ab.deflections_per100,
            "loose balls per100 total possessions": c.s2(
                "trait", "loose balls per100 total possessions", c.col("LOOSE_BALLS_RECOVERED"),
                (c.col("OFF_POSS") + c.col("DEF_POSS")) / 100.0),
            "charges drawn per100": ab.charges_per100,
            "screen assists per100": ab.per100_off("SCREEN_ASSISTS per100", c.col("SCREEN_ASSISTS")),
            "contested shots share": c.s1("trait", "contested shots / opponent FGA on floor",
                                          c.col("CONTESTED_SHOTS"), c.col("opp_fga")),
            "offensive-rebound crash rate": c.s1("trait", "OREB_CHANCES / team missed FGA on floor",
                                                 c.col("OREB_CHANCES"), c.col("team_missed_fga")),
        }
        zs = {k: Z(v) for k, v in comps.items()}
        for k in comps:
            c.log("trait:hustle", k, comps[k], zs[k])
        value = np.mean(list(zs.values()), axis=0)
        return value, zstd(value)

    def streaky(self):
        s = self.lg.shots.copy()
        s["clock"] = s["MINUTES_REMAINING"] * 60 + s["SECONDS_REMAINING"]
        s = s.sort_values(["GAME_DATE", "GAME_ID", "PERIOD", "clock", "GAME_EVENT_ID"],
                          ascending=[True, True, True, False, True])
        z_runs = {int(p): runs_test_z(g["SHOT_MADE_FLAG"].to_numpy()) for p, g in s.groupby("PLAYER_ID")}
        z = -self.c.series(pd.Series(z_runs, dtype=float), fill=0.0)
        self.c.log("trait:streaky", "-z_runs", z, z)
        return z, z


def derive_traits(ctx, lg, attr_builder, tendencies, all_ids):
    """Returns (rows, failures); non-exposed players get no trait (z = 0)."""
    b = TraitBuilder(ctx, lg, attr_builder, tendencies)
    frames, failures = [], {}
    missing = pd.Index(all_ids).difference(ctx.ids)
    for key in TRAITS:
        try:
            value, z = (np.asarray(v, float) for v in getattr(b, key)())
            if np.any(~np.isfinite(z)):
                raise DerivationError("z undefined for some players")
        except Exception as e:      # noqa: BLE001 - reported per field
            failures[key] = ("abort" if type(e).__name__ == "ProportionViolation" else "failed",
                             f"{type(e).__name__}: {e}")
            continue
        t = tier(z)
        names = TIER_NAMES[key]
        frames.append(pd.DataFrame({"player_id": ctx.ids, "trait": key, "value": value, "z_score": z,
                                    "tier": t, "tier_name": [names[i + 2] for i in t]}))
        if len(missing):
            frames.append(pd.DataFrame({"player_id": missing, "trait": key, "value": np.nan,
                                        "z_score": 0.0, "tier": 0, "tier_name": None}))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["player_id", "trait", "value", "z_score", "tier", "tier_name"])
    return out, failures
