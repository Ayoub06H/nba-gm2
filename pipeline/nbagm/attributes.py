"""The 27 rated attributes of doc 02.

Every attribute is computed the same way for every player in the population
(rostered players with exposure): real statistics, shrunk by the family doc 02
names, combined into the Score the attribute's row defines, then
Rating = 99 x mid-rank percentile of Score. Shared intermediate results (expected
value models, ridge regressions, contest accounting) are computed once and
reused, so a statistic that feeds several attributes is the same number in each.
"""

from functools import cached_property

import numpy as np
import pandas as pd

from . import models
from .common import Z, DerivationError, pct, rating, safe_div, zstd
from .league import COMBINE_TESTS

ATTRIBUTES = (
    "driving_layup", "driving_dunk", "standing_dunk", "touch", "post_scoring",
    "three_pointer", "mid_range", "free_throw",
    "ball_handle", "passing_accuracy", "vision", "offensive_iq",
    "offensive_rebounding", "defensive_rebounding", "steals", "shot_blocking",
    "off_ball_defense", "on_ball_defense", "post_defense", "rim_protection", "defensive_iq",
    "speed", "acceleration", "lateral_quickness", "vertical", "strength", "stamina",
)
PLACEHOLDER_RATING = 40.0     # doc 02 Population: temporary value for players with no exposure

RIM_ZONES = ("Restricted Area", "In The Paint (Non-RA)")
TOUCH_WORDS = ("layup", "finger roll", "hook", "floating", "floater", "tip", "putback", "bank")
TIME_TESTS = ("THREE_QUARTER_SPRINT", "LANE_AGILITY_TIME", "MODIFIED_LANE_AGILITY_TIME")


class BucketError(DerivationError):
    pass


def shot_bucket(action_type, zone):
    """Doc 02 Rim Scoring buckets, applied in order (case-insensitive)."""
    a = str(action_type).lower()
    if "dunk" in a:
        return "DRIVING_DUNK" if a.startswith(("driving", "running")) else "STANDING_DUNK"
    if ("layup" in a or "finger roll" in a) and a.startswith(("driving", "running")):
        return "DRIVING_LAYUP"
    if zone in RIM_ZONES and any(w in a for w in TOUCH_WORDS):
        return "TOUCH"
    return None


def classify_shots(shots):
    b = [shot_bucket(a, z) for a, z in zip(shots["ACTION_TYPE"], shots["SHOT_ZONE_BASIC"])]
    shots = shots.assign(bucket=b)
    left = shots[shots["bucket"].isna() & shots["SHOT_ZONE_BASIC"].isin(RIM_ZONES)
                 & ~shots["ACTION_TYPE"].str.lower().str.contains("jump shot")]
    if len(left):
        counts = left["ACTION_TYPE"].value_counts()
        raise BucketError("Rim Scoring buckets: shots in the Restricted Area / In The Paint "
                          "(Non-RA) zones that no rule classifies and that are not jump shots: "
                          + "; ".join(f"{a} ({n})" for a, n in counts.items()))
    return shots



class AttributeBuilder:
    def __init__(self, ctx, lg):
        self.c = ctx
        self.lg = lg
        self.off = ctx.col("OFF_POSS") / 100.0      # exposure for per100 offense rates
        self.de = ctx.col("DEF_POSS") / 100.0
        self.roster = lg.roster.set_index("player_id").reindex(ctx.ids)

    # ------------------------------------------------------------------ helpers
    def per100_off(self, name, counts):
        return self.c.s2("attribute", name, counts, self.off)

    def per100_def(self, name, counts):
        return self.c.s2("attribute", name, counts, self.de)

    def log(self, fld, comps):
        """comps: {component name: (value, Z or None)}"""
        for name, (v, zz) in comps.items():
            self.c.log(fld, name, v, zz)

    def by_player(self, values):
        return self.c.series(values, fill=0.0)

    # ------------------------------------------------------------------ shared pieces
    @cached_property
    def shots(self):
        return classify_shots(self.lg.shots)

    @cached_property
    def ft_star(self):
        return self.c.s1("attribute", "FT%", self.c.col("FTM"), self.c.col("FTA"))

    def e1_component(self, name, bucket_shots):
        """Doc 02 E1: d = (makes - sum p_hat)/n, s^2 = sum p_hat(1-p_hat)/n^2, then S3."""
        model = models.fit_shot_model(bucket_shots, name=name)
        self.c.audit.models.append((name, "lambda", model.lam))
        self.c.audit.models.append((name, "n_shots", model.n_shots))
        p = model.predict(bucket_shots)
        g = pd.DataFrame({"pid": bucket_shots["PLAYER_ID"].to_numpy(), "y": bucket_shots["SHOT_MADE_FLAG"].to_numpy(),
                          "p": p, "v": p * (1 - p)}).groupby("pid").agg(n=("y", "size"), y=("y", "sum"),
                                                                     p=("p", "sum"), v=("v", "sum"))
        n = self.c.series(g["n"])
        d = safe_div(self.c.series(g["y"]) - self.c.series(g["p"]), n)
        s2_ = safe_div(self.c.series(g["v"]), n ** 2)
        out, _ = self.c.s3("attribute", name, d, s2_)
        return out

    def bucket_counts(self, bucket, made_only=False):
        s = self.shots[self.shots["bucket"] == bucket]
        if made_only:
            s = s[s["SHOT_MADE_FLAG"] == 1]
        return self.by_player(s.groupby("PLAYER_ID").size())

    @cached_property
    def zone_value(self):
        """Doc 02 E4: u(z) = (2 FG2M + 3 FG3M) / FGA per SHOT_ZONE_BASIC zone, plus u_rim
        (SHOT_DISTANCE < 6) and u_other."""
        s = self.lg.shots
        pts = s["SHOT_MADE_FLAG"] * np.where(s["SHOT_TYPE"].str.startswith("3"), 3, 2)
        u = pts.groupby(s["SHOT_ZONE_BASIC"]).sum() / s.groupby("SHOT_ZONE_BASIC").size()
        rim = s["SHOT_DISTANCE"] < 6
        u_rim, u_other = pts[rim].sum() / rim.sum(), pts[~rim].sum() / (~rim).sum()
        for z, v in u.items():
            self.c.audit.models.append(("E4", f"u[{z}]", float(v)))
        self.c.audit.models.append(("E4", "u_rim", float(u_rim)))
        self.c.audit.models.append(("E4", "u_other", float(u_other)))
        return u, float(u_rim), float(u_other)

    @cached_property
    def shot_u(self):
        u, _, _ = self.zone_value
        return self.lg.shots.assign(u=self.lg.shots["SHOT_ZONE_BASIC"].map(u))

    def u_delta(self, name, frame, key):
        """Mean u of a player's shots minus the league mean of the same shots; sampling
        variance = league variance of u / n (doc 02); S3."""
        mu, var = frame["u"].mean(), frame["u"].var(ddof=0)
        g = frame.groupby(key)["u"].agg(["mean", "size"])
        n = self.c.series(g["size"])
        d = np.where(n > 0, self.c.series(g["mean"], fill=np.nan) - mu, np.nan)
        out, _ = self.c.s3("attribute", name, d, safe_div(np.full(len(n), var), n))
        return out

    @cached_property
    def assist_quality(self):
        a = self.lg.assists.merge(self.shot_u[["GAME_ID", "GAME_EVENT_ID", "u"]],
                                  left_on=["game_id", "event_id"],
                                  right_on=["GAME_ID", "GAME_EVENT_ID"], how="inner")
        return self.u_delta("assisted-shot quality d", a, "assister")

    @cached_property
    def shot_choice(self):
        return self.u_delta("shot-choice value d", self.shot_u, "PLAYER_ID")

    @cached_property
    def load(self):
        """Ben Taylor's Box Creation and Offensive Load, all terms per 100 of his own
        on-floor team possessions (doc 02 shared definitions)."""
        c = self.c
        per = lambda col: safe_div(c.col(col), self.off)            # noqa: E731
        ast, pts, tov, fga, fta, tpa = (per(k) for k in ("AST", "PTS", "TOV", "FGA", "FTA", "FG3A"))
        tp_pct = np.where(c.col("FG3A") > 0, safe_div(c.col("FG3M"), c.col("FG3A")), 0.0)
        prof = (2 / (1 + np.exp(-tpa)) - 1) * tp_pct
        bc = ast * 0.1843 + (pts + tov) * 0.0969 - 2.3021 * prof + 0.0582 * (ast * (pts + tov) * prof) - 1.1942
        ol = ((ast - 0.38 * bc) * 0.75) + fga + fta * 0.44 + bc + tov
        return bc, ol

    @cached_property
    def ol_star(self):
        _bc, ol = self.load
        return self.per100_off("Offensive Load per100", ol * self.off)

    @cached_property
    def creation(self):
        c = self.c
        poss = c.col("SYN_Isolation_POSS") + c.col("SYN_PRBallHandler_POSS")
        pts = c.col("SYN_Isolation_PTS") + c.col("SYN_PRBallHandler_PTS")
        return poss, pts

    @cached_property
    def creation_per100(self):
        return self.per100_off("creation possessions per100", self.creation[0])

    @cached_property
    def drives_per100(self):
        return self.per100_off("DRIVES per100", self.c.col("DRIVES"))

    @cached_property
    def ast_adj_per100(self):
        return self.per100_off("AST_ADJ per100", self.c.col("AST_ADJ"))

    def e3_rr(self, name, observed, exposure, covariates, cov_names):
        fit = models.fit_poisson(observed, exposure, covariates, cov_names, name=name)
        for k, b in zip(("intercept",) + tuple(cov_names), fit.coef):
            self.c.audit.models.append((name, k, float(b)))
        ok = (np.asarray(exposure) > 0) & np.all([np.isfinite(x) for x in covariates], axis=0)
        e = np.where(ok, fit.expected(np.where(ok, exposure, 0.0),
                                      [np.where(ok, x, 0.0) for x in covariates]), 0.0)
        return self.c.s4("attribute", name, observed, e)

    # --- defense: contest accounting
    @cached_property
    def contests(self):
        d = self.lg.pt_defend.pivot_table(index="player_id", columns="category", values=["A", "M", "E"],
                                          aggfunc="sum")
        out = {}
        for cat in ("Overall", "P3", "P2", "R"):
            out[cat] = {k: self.c.series(d[(k, cat)]) if (k, cat) in d.columns else
                        np.zeros(len(self.c.ids)) for k in ("A", "M", "E")}
        return out

    def delta_star(self, cat):
        """Points saved per attempt in a contest category, S3 (doc 02)."""
        pts = 3.0 if cat == "P3" else 2.0
        a, m, e = (self.contests[cat][k] for k in ("A", "M", "E"))
        qbar = safe_div(e, a)
        d = safe_div(pts * (e - m), a)
        s2_ = safe_div(pts ** 2 * qbar * (1 - qbar), a)
        out, _ = self.c.s3("attribute", f"delta_{cat}", d, s2_)
        return out

    @cached_property
    def a_star(self):
        return {cat: self.per100_def(f"D_FGA {cat} per100", self.contests[cat]["A"])
                for cat in ("Overall", "P3", "P2", "R")}

    @cached_property
    def foul_cost(self):
        """FC_i = f_bar * (phi_i* - phi_bar) * DFGA_overall per100 (doc 02)."""
        lc = self.lg.league_counts
        if lc.get("shooting_fouls", 0) <= 0:
            raise DerivationError("no shooting fouls found in play-by-play")
        f_bar = lc["shooting_foul_ft_points"] / lc["shooting_fouls"]
        sf = self.c.col("shooting_fouls")
        a = self.contests["Overall"]["A"]
        phi = self.c.s1("attribute", "FOUL%", sf, a + sf)
        phi_bar = phi.mean()
        self.c.audit.models.append(("foul cost", "f_bar", float(f_bar)))
        self.c.audit.models.append(("foul cost", "phi_bar", float(phi_bar)))
        return f_bar * (phi - phi_bar) * self.a_star["Overall"]

    def contest_share(self, cats):
        a = self.contests["Overall"]["A"]
        bad = self.c.ids[a <= 0]
        if len(bad):
            raise DerivationError("foul-cost allocation (doc 02) divides by a player's D_FGA Overall, "
                                  f"which is 0 for {len(bad)} player(s) with defensive exposure: "
                                  f"{list(bad[:20])}")
        return sum(self.contests[c]["A"] for c in cats) / a

    @cached_property
    def blk_pct(self):
        return self.c.s1("attribute", "BLK%", self.c.col("pbp_blocks"), self.c.col("opp_fg2a"))

    @cached_property
    def blk_per100(self):
        return self.per100_def("BLK per100", self.c.col("pbp_blocks"))

    @cached_property
    def deflections_per100(self):
        return self.per100_def("deflections per100", self.c.col("DEFLECTIONS"))

    @cached_property
    def charges_per100(self):
        return self.per100_def("charges drawn per100", self.c.col("CHARGES_DRAWN"))

    @cached_property
    def contested_per100(self):
        return self.per100_def("contested shots per100", self.c.col("CONTESTED_SHOTS"))

    @cached_property
    def stl_pct(self):
        return self.c.s1("attribute", "STL%", self.c.col("STL"), self.c.col("DEF_POSS"))

    # --- ridge regressions on stints
    @cached_property
    def stint_rows(self):
        st = self.lg.stints
        u, _, _ = self.zone_value
        sh = self.lg.shots.set_index(["GAME_ID", "GAME_EVENT_ID"])
        zone = sh["SHOT_ZONE_BASIC"].map(u)
        rim = (sh["SHOT_DISTANCE"] < 6).astype(float)
        uq, rq = zone.to_dict(), rim.to_dict()
        sq, ra, matched, total = [], [], 0, 0
        for gid, ids in zip(st["game_id"], st["shot_ids"]):
            su = sr = 0.0
            for e in ids:
                total += 1
                k = (gid, e)
                if k in uq:
                    matched += 1
                    su += uq[k]
                    sr += rq[k]
            sq.append(su)
            ra.append(sr)
        self.c.audit.models.append(("stint ridge", "stint FGA matched to shot chart",
                                    matched / total if total else 1.0))
        return st.assign(sq=sq, rim=ra)

    def ridge(self, name, y_col):
        st = self.stint_rows
        rows = pd.DataFrame({"game_id": st["game_id"], "offense": st["offense"],
                             "defense": st["defense"], "w": st["poss"],
                             "y": 100.0 * safe_div(st[y_col], st["poss"])})
        r = models.fit_stint_ridge(rows, name=name)
        self.c.audit.models.append((name, "lambda", r.lam))
        self.c.audit.models.append((name, "intercept", r.intercept))
        self.c.audit.models.append((name, "stint rows", r.n_rows))
        missing = self.c.ids.difference(r.offense.index)
        if len(missing):
            raise DerivationError(f"{name}: {len(missing)} player(s) with exposure appear in no "
                                  f"stint with a known ten-man lineup: {list(missing[:20])}")
        return r

    @cached_property
    def rapm(self):
        return self.ridge("RAPM (points)", "pts")

    @cached_property
    def sq_ridge(self):
        return self.ridge("shot-quality ridge", "sq")

    @cached_property
    def rim_ridge(self):
        return self.ridge("rim-attempts ridge", "rim")

    # --- physicals
    @cached_property
    def wingspan(self):
        return self.roster["wingspan_in"].to_numpy(float)

    def onehot_position(self, ids=None):
        r = self.lg.roster.set_index("player_id")
        labels = r["position"] if ids is None else r.loc[ids, "position"]
        return models.one_hot(labels)

    @cached_property
    def tests_final(self):
        """Doc 02 Physicals: own combine result, else a ridge prediction from height,
        weight, wingspan, age and published position (one-hot), fit on rostered players
        with the test."""
        r = self.lg.roster.set_index("player_id")
        feats = pd.DataFrame({"h": r["height_in"], "w": r["weight_lb"], "ws": r["wingspan_in"],
                              "age": r["age"]})
        bad = feats.index[feats.isna().any(axis=1)]
        if len(bad):
            raise DerivationError(f"combine-test imputation: missing height/weight/wingspan/age for "
                                  f"{list(bad[:20])}")
        X = np.column_stack([feats.to_numpy(float), models.one_hot(r["position"])])
        out = {}
        comb = self.lg.combine.reindex(r.index)
        for t in COMBINE_TESTS:
            have = comb[t].notna().to_numpy()
            imp = models.fit_ridge_imputer(X[have], comb[t].to_numpy(float)[have], name=t)
            self.c.audit.models.append((f"{t} imputation", "lambda", imp.lam))
            self.c.audit.models.append((f"{t} imputation", "n_fit", imp.n_fit))
            final = np.where(have, comb[t].to_numpy(float), imp.predict(X))
            out[t] = pd.Series(final, index=r.index)
        return out

    def test_z(self, t):
        v = self.tests_final[t].reindex(self.c.ids).to_numpy(float)
        z = zstd(v)
        return -z if t in TIME_TESTS else z

    @cached_property
    def tracking_design(self):
        pace = self.lg.team_pace.reindex(self.roster["team_id"]).to_numpy(float)
        age = self.roster["age"].to_numpy(float)
        if np.any(~np.isfinite(pace)) or np.any(~np.isfinite(age)):
            raise DerivationError("tracking residual design: missing team pace or age")
        return np.column_stack([self.onehot_position(self.c.ids), age, pace])

    def tracking_residual_z(self, values, name):
        v = np.asarray(values, float)
        if np.any(~np.isfinite(v)):
            bad = list(self.c.ids[~np.isfinite(v)][:20])
            raise DerivationError(f"{name}: undefined for {len(bad)}+ player(s) with exposure: {bad}")
        return zstd(models.ols_residuals(v, self.tracking_design))

    # ------------------------------------------------------------------ attributes
    def driving_layup(self):
        s = self.shots[self.shots["bucket"] == "DRIVING_LAYUP"]
        eff = self.e1_component("E1 DRIVING_LAYUP d", s)
        vol = self.per100_off("DRIVING_LAYUP FGA per100", self.bucket_counts("DRIVING_LAYUP"))
        fta = self.per100_off("DRIVE_FTA per100", self.c.col("DRIVE_FTA"))
        zs = [Z(eff), Z(vol), Z(fta)]
        self.log("driving_layup", {"efficiency d*": (eff, zs[0]), "attempts per100": (vol, zs[1]),
                                   "drive FTA per100": (fta, zs[2])})
        return np.mean(zs, axis=0)

    def driving_dunk(self):
        v = self.per100_off("DRIVING_DUNK makes per100", self.bucket_counts("DRIVING_DUNK", True))
        self.log("driving_dunk", {"makes per100": (v, Z(v))})
        return Z(v)

    def standing_dunk(self):
        v = self.per100_off("STANDING_DUNK makes per100", self.bucket_counts("STANDING_DUNK", True))
        self.log("standing_dunk", {"makes per100": (v, Z(v))})
        return Z(v)

    def touch(self):
        s = self.shots[self.shots["bucket"] == "TOUCH"]
        eff = self.e1_component("E1 TOUCH d", s)
        vol = self.per100_off("TOUCH FGA per100", self.bucket_counts("TOUCH"))
        zs = [Z(eff), Z(vol), Z(self.ft_star)]
        self.log("touch", {"efficiency d*": (eff, zs[0]), "attempts per100": (vol, zs[1]),
                           "FT%*": (self.ft_star, zs[2])})
        return np.mean(zs, axis=0)

    def post_scoring(self):
        ppp = self.c.s2("attribute", "Postup PPP", self.c.col("SYN_Postup_PTS"), self.c.col("SYN_Postup_POSS"))
        vol = self.per100_off("Postup possessions per100", self.c.col("SYN_Postup_POSS"))
        self.log("post_scoring", {"PPP*": (ppp, Z(ppp)), "possessions per100": (vol, Z(vol))})
        return 0.5 * Z(ppp) + 0.5 * Z(vol)

    def three_pointer(self):
        cells = self.lg.pt_shot_cells
        q = cells.groupby(["general_range", "def_dist"])[["FG3M", "FG3A"]].sum()
        q = (q["FG3M"] / q["FG3A"]).rename("q")
        for (g, d), v in q.items():
            self.c.audit.models.append(("E2", f"q[{g} | {d}]", float(v)))
        c = cells.join(q, on=["general_range", "def_dist"])
        c = c.assign(exp=c["FG3A"] * c["q"], var=c["FG3A"] * c["q"] * (1 - c["q"]))
        g = c.groupby("player_id")[["FG3M", "FG3A", "exp", "var"]].sum()
        a = self.c.series(g["FG3A"])
        d = safe_div(self.c.series(g["FG3M"]) - self.c.series(g["exp"]), a)
        eff, _ = self.c.s3("attribute", "E2 3P d", d, safe_div(self.c.series(g["var"]), a ** 2))
        vol = self.per100_off("3PA per100", self.c.col("FG3A"))
        zs = [Z(eff), Z(vol), Z(self.ft_star)]
        self.log("three_pointer", {"efficiency d*": (eff, zs[0]), "3PA per100": (vol, zs[1]),
                                   "FT%*": (self.ft_star, zs[2])})
        return np.mean(zs, axis=0)

    def mid_range(self):
        s = self.shots[self.shots["SHOT_ZONE_BASIC"] == "Mid-Range"]
        eff = self.e1_component("E1 Mid-Range d", s)
        vol = self.per100_off("Mid-Range FGA per100", self.by_player(s.groupby("PLAYER_ID").size()))
        zs = [Z(eff), Z(vol), Z(self.ft_star)]
        self.log("mid_range", {"efficiency d*": (eff, zs[0]), "attempts per100": (vol, zs[1]),
                               "FT%*": (self.ft_star, zs[2])})
        return np.mean(zs, axis=0)

    def free_throw(self):
        self.log("free_throw", {"FT%*": (self.ft_star, None)})
        return self.ft_star

    def ball_handle(self):
        rr = self.e3_rr("E3 handling turnovers", self.c.col("tov_handling"), self.c.col("DRIBBLES"),
                        [np.log(self.ol_star), self.creation_per100],
                        ["ln(Offensive Load per100)", "creation possessions per100"])
        poss, pts = self.creation
        ppp = self.c.s2("attribute", "creation PPP", pts, poss)
        vol = [Z(self.creation_per100), Z(self.ol_star), Z(self.drives_per100)]
        self.log("ball_handle", {"handling turnovers RR*": (rr, Z(-rr)), "creation PPP*": (ppp, Z(ppp)),
                                 "creation per100": (self.creation_per100, vol[0]),
                                 "Offensive Load per100": (self.ol_star, vol[1]),
                                 "drives per100": (self.drives_per100, vol[2])})
        return (Z(-rr) + Z(ppp) + np.mean(vol, axis=0)) / 3.0

    def passing_accuracy(self):
        passes = self.c.col("PASSES_MADE")
        risk = safe_div(self.c.col("POTENTIAL_AST"), passes)
        rr = self.e3_rr("E3 bad-pass turnovers", self.c.col("tov_bad_pass"), passes, [risk],
                        ["POTENTIAL_AST / PASSES_MADE"])
        p100 = self.per100_off("PASSES_MADE per100", passes)
        vol = [Z(p100), Z(self.ast_adj_per100)]
        self.log("passing_accuracy", {"bad-pass turnovers RR*": (rr, Z(-rr)),
                                      "passes per100": (p100, vol[0]),
                                      "AST_ADJ per100": (self.ast_adj_per100, vol[1])})
        return 0.5 * Z(-rr) + 0.5 * np.mean(vol, axis=0)

    def vision(self):
        pot = self.per100_off("POTENTIAL_AST per100", self.c.col("POTENTIAL_AST"))
        apc = self.per100_off("AST_POINTS_CREATED per100", self.c.col("AST_POINTS_CREATED"))
        vol = [Z(pot), Z(self.ast_adj_per100), Z(apc)]
        q = self.assist_quality
        self.log("vision", {"assisted-shot quality d*": (q, Z(q)), "potential assists per100": (pot, vol[0]),
                            "AST_ADJ per100": (self.ast_adj_per100, vol[1]),
                            "AST_POINTS_CREATED per100": (apc, vol[2])})
        return 0.5 * Z(q) + 0.5 * np.mean(vol, axis=0)

    def rule_a(self, fld, comps, target):
        names = list(comps)
        Zm = np.column_stack([Z(comps[n]) for n in names])
        w = models.rule_a_weights(Zm, target)
        for n, wi, col in zip(names, w, Zm.T):
            self.c.audit.weights.append((fld, n, float(wi)))
            self.c.log(fld, n, comps[n], col)
            if wi == 0:
                self.c.audit.note(fld, f"Rule A: component '{n}' got weight 0 and drops out")
        return Zm @ w

    def offensive_iq(self):
        dec = self.e3_rr("E3 decision turnovers", self.c.col("tov_decision"), self.c.col("OFF_POSS"),
                         [np.log(self.ol_star)], ["ln(Offensive Load per100)"])
        bc, _ol = self.load
        syn = sum(self.c.col(f"SYN_{k}_PTS") for k in ("Cut", "OffScreen", "Handoff"))
        comps = {
            "shot-choice value d*": self.shot_choice,
            "decision turnovers RR* (negated)": -dec,
            "SCREEN_ASSISTS per100": self.per100_off("SCREEN_ASSISTS per100", self.c.col("SCREEN_ASSISTS")),
            "SCREEN_AST_PTS per100": self.per100_off("SCREEN_AST_PTS per100", self.c.col("SCREEN_AST_PTS")),
            "Cut+OffScreen+Handoff points per100": self.per100_off("Cut+OffScreen+Handoff PTS per100", syn),
            "assisted-shot quality d*": self.assist_quality,
            "AST_ADJ per100": self.ast_adj_per100,
            "Box Creation per100": bc,
        }
        target = self.c.series(self.rapm.offense, fill=np.nan)
        return self.rule_a("offensive_iq", comps, target)

    def _rebounding(self, fld, side):
        c = self.c
        if not self.lg.league_counts.get("rebound_chances_available", True):
            pct_ = (c.s1("attribute", "ORB%", c.col("OREB"), c.col("team_oreb") + c.col("opp_dreb"))
                    if side == "O" else
                    c.s1("attribute", "DRB%", c.col("DREB"), c.col("team_dreb") + c.col("opp_oreb")))
            c.audit.note(fld, "rebound-chance columns missing: ORB%/DRB% alone (doc 02 fallback)")
            self.log(fld, {f"{side}RB%*": (pct_, Z(pct_))})
            return Z(pct_)
        if side == "O":
            conv = c.s1("attribute", "OREB conversion", c.col("TRK_OREB"),
                        c.col("OREB_CHANCES") - c.col("OREB_CHANCE_DEFER"))
            share = c.s1("attribute", "ORB%", c.col("OREB"), c.col("team_oreb") + c.col("opp_dreb"))
            vols = {"OREB_CHANCES per100": self.per100_off("OREB_CHANCES per100", c.col("OREB_CHANCES")),
                    "OFF_LOOSE_BALLS_RECOVERED per100": self.per100_off(
                        "OFF_LOOSE_BALLS_RECOVERED per100", c.col("OFF_LOOSE_BALLS_RECOVERED")),
                    "OFF_BOXOUTS per100": self.per100_off("OFF_BOXOUTS per100", c.col("OFF_BOXOUTS"))}
        else:
            conv = c.s1("attribute", "DREB conversion", c.col("TRK_DREB"),
                        c.col("DREB_CHANCES") - c.col("DREB_CHANCE_DEFER"))
            share = c.s1("attribute", "DRB%", c.col("DREB"), c.col("team_dreb") + c.col("opp_oreb"))
            vols = {"DREB_CHANCES per100": self.per100_def("DREB_CHANCES per100", c.col("DREB_CHANCES")),
                    "DEF_LOOSE_BALLS_RECOVERED per100": self.per100_def(
                        "DEF_LOOSE_BALLS_RECOVERED per100", c.col("DEF_LOOSE_BALLS_RECOVERED")),
                    "DEF_BOXOUTS per100": self.per100_def("DEF_BOXOUTS per100", c.col("DEF_BOXOUTS"))}
        eff = [Z(conv), Z(share)]
        vz = {k: Z(v) for k, v in vols.items()}
        self.log(fld, {"conversion*": (conv, eff[0]), f"{side}RB%*": (share, eff[1]),
                       **{k: (vols[k], vz[k]) for k in vols}})
        return 0.5 * np.mean(eff, axis=0) + 0.5 * np.mean(list(vz.values()), axis=0)

    def offensive_rebounding(self):
        return self._rebounding("offensive_rebounding", "O")

    def defensive_rebounding(self):
        return self._rebounding("defensive_rebounding", "D")

    def steals(self):
        self.log("steals", {"STL%*": (self.stl_pct, Z(self.stl_pct)),
                            "deflections per100": (self.deflections_per100, Z(self.deflections_per100))})
        return 0.5 * Z(self.stl_pct) + 0.5 * Z(self.deflections_per100)

    def shot_blocking(self):
        lc = self.lg.league_counts
        league_a = self.lg.pt_defend.groupby("category")["A"].sum()
        expected = np.zeros(len(self.c.ids))
        for cat in ("R", "P2", "P3"):
            if league_a.get(cat, 0) <= 0:
                raise DerivationError(f"E5: no league D_FGA in category {cat}")
            b = lc[f"pbp_blocks_{cat}"] / league_a[cat]
            self.c.audit.models.append(("E5", f"b[{cat}]", float(b)))
            expected += self.contests[cat]["A"] * b
        rr = self.c.s4("attribute", "RR_BLK", self.c.col("pbp_blocks"), expected)
        vol = [Z(self.blk_pct), Z(self.blk_per100)]
        self.log("shot_blocking", {"RR_BLK*": (rr, Z(rr)), "BLK%*": (self.blk_pct, vol[0]),
                                   "BLK per100*": (self.blk_per100, vol[1])})
        return 0.5 * Z(rr) + 0.5 * np.mean(vol, axis=0)

    def on_ball_defense(self):
        d3, d2 = self.delta_star("P3"), self.delta_star("P2")
        fc = self.foul_cost * self.contest_share(("P3", "P2"))
        net = self.a_star["P3"] * d3 + self.a_star["P2"] * d2 - fc
        self.log("on_ball_defense", {"delta_P3*": (d3, None), "delta_P2*": (d2, None),
                                     "D_FGA P3 per100*": (self.a_star["P3"], None),
                                     "D_FGA P2 per100*": (self.a_star["P2"], None),
                                     "perimeter foul cost": (fc, None),
                                     "net perimeter points saved per100": (net, None)})
        return net

    def post_defense(self):
        c = self.c
        pts, poss = c.col("SYN_D_Postup_PTS"), c.col("SYN_D_Postup_POSS")
        lg_post = self.lg.inputs[["SYN_D_Postup_PTS", "SYN_D_Postup_POSS"]].sum()
        league_ppp = lg_post["SYN_D_Postup_PTS"] / lg_post["SYN_D_Postup_POSS"]
        self.c.audit.models.append(("post defense", "league PPP", float(league_ppp)))
        ppp = c.s2("attribute", "defensive Postup PPP", pts, poss)
        vol = self.per100_def("defensive Postup possessions per100", poss)
        v = vol * (league_ppp - ppp)
        self.log("post_defense", {"PPP allowed*": (ppp, None), "possessions per100*": (vol, None),
                                  "points saved per100": (v, None)})
        return v

    def rim_protection(self):
        dr = self.delta_star("R")
        contest = self.a_star["R"] * dr
        _, u_rim, u_other = self.zone_value
        gamma = self.c.series(self.rim_ridge.defense, fill=np.nan)
        deter = -gamma * (u_rim - u_other)
        fc = self.foul_cost * self.contest_share(("R",))
        v = contest + deter - fc
        self.log("rim_protection", {"contest (A_R* x delta_R*)": (contest, None),
                                    "deterrence": (deter, None), "rim foul cost": (fc, None),
                                    "net rim points saved per100": (v, None)})
        return v

    def off_ball_defense(self):
        help_ = models.ols_residuals(self.contested_per100, self.a_star["Overall"])
        comps = {"help contests (residual)": help_, "BLK per100*": self.blk_per100,
                 "deflections per100*": self.deflections_per100, "charges drawn per100*": self.charges_per100}
        zs = {k: Z(v) for k, v in comps.items()}
        self.log("off_ball_defense", {k: (comps[k], zs[k]) for k in comps})
        return np.mean(list(zs.values()), axis=0)

    def defensive_iq(self):
        c = self.c
        stop = c.col("STL") + c.col("offensive_fouls_drawn") + c.col("pbp_blocks_recovered")
        comps = {
            "shot-quality suppression (negated defense coefficient)":
                -self.c.series(self.sq_ridge.defense, fill=np.nan),
            "STOP per100": self.per100_def("STOP per100", stop),
            "non-shooting defensive fouls per100 (negated)":
                -self.per100_def("non-shooting defensive fouls per100", c.col("nonshooting_def_fouls")),
            "contested shots per100": self.contested_per100,
            "deflections per100": self.deflections_per100,
            "charges drawn per100": self.charges_per100,
            "loose balls recovered per100": self.per100_def("loose balls recovered per100 DEFPOSS",
                                                            c.col("LOOSE_BALLS_RECOVERED")),
            "BLK%*": self.blk_pct,
            "rim delta_R*": self.delta_star("R"),
        }
        target = -self.c.series(self.rapm.defense, fill=np.nan)
        return self.rule_a("defensive_iq", comps, target)

    # --- physicals (Rule B means of z-scores)
    def _rule_b(self, fld, comps):
        self.log(fld, {k: (None if v is None else v, z) for k, (v, z) in comps.items()})
        return np.mean([z for (_v, z) in comps.values()], axis=0)

    def speed(self):
        z_off = self.tracking_residual_z(self.c.col("AVG_SPEED_OFF"), "AVG_SPEED_OFF")
        return self._rule_b("speed", {
            "-z(THREE_QUARTER_SPRINT)": (self.tests_final["THREE_QUARTER_SPRINT"].reindex(self.c.ids),
                                         self.test_z("THREE_QUARTER_SPRINT")),
            "z(AVG_SPEED_OFF residual)": (self.c.col("AVG_SPEED_OFF"), z_off)})

    def acceleration(self):
        z_dr = self.tracking_residual_z(self.drives_per100, "DRIVES per100")
        return self._rule_b("acceleration", {
            "-z(THREE_QUARTER_SPRINT)": (self.tests_final["THREE_QUARTER_SPRINT"].reindex(self.c.ids),
                                         self.test_z("THREE_QUARTER_SPRINT")),
            "-z(MODIFIED_LANE_AGILITY_TIME)": (self.tests_final["MODIFIED_LANE_AGILITY_TIME"].reindex(self.c.ids),
                                               self.test_z("MODIFIED_LANE_AGILITY_TIME")),
            "z(STANDING_VERTICAL_LEAP)": (self.tests_final["STANDING_VERTICAL_LEAP"].reindex(self.c.ids),
                                          self.test_z("STANDING_VERTICAL_LEAP")),
            "z(DRIVES per100 residual)": (self.drives_per100, z_dr)})

    def lateral_quickness(self):
        z_def = self.tracking_residual_z(self.c.col("AVG_SPEED_DEF"), "AVG_SPEED_DEF")
        return self._rule_b("lateral_quickness", {
            "-z(LANE_AGILITY_TIME)": (self.tests_final["LANE_AGILITY_TIME"].reindex(self.c.ids),
                                      self.test_z("LANE_AGILITY_TIME")),
            "-z(MODIFIED_LANE_AGILITY_TIME)": (self.tests_final["MODIFIED_LANE_AGILITY_TIME"].reindex(self.c.ids),
                                               self.test_z("MODIFIED_LANE_AGILITY_TIME")),
            "z(AVG_SPEED_DEF residual)": (self.c.col("AVG_SPEED_DEF"), z_def)})

    def vertical(self):
        made = self.bucket_counts("DRIVING_DUNK", True) + self.bucket_counts("STANDING_DUNK", True)
        above = self.per100_off("above-rim makes per100", made)
        design = np.column_stack([self.roster["height_in"].to_numpy(float), self.onehot_position(self.c.ids)])
        z_above = zstd(models.ols_residuals(above, design))
        return self._rule_b("vertical", {
            "z(MAX_VERTICAL_LEAP)": (self.tests_final["MAX_VERTICAL_LEAP"].reindex(self.c.ids),
                                     self.test_z("MAX_VERTICAL_LEAP")),
            "z(STANDING_VERTICAL_LEAP)": (self.tests_final["STANDING_VERTICAL_LEAP"].reindex(self.c.ids),
                                          self.test_z("STANDING_VERTICAL_LEAP")),
            "z(above-rim finishing residual)": (above, z_above)})

    def strength(self):
        w = self.roster["weight_lb"].to_numpy(float)
        return self._rule_b("strength", {
            "z(WEIGHT)": (w, zstd(w)),
            "z(BENCH_PRESS)": (self.tests_final["BENCH_PRESS"].reindex(self.c.ids), self.test_z("BENCH_PRESS"))})

    def stamina(self):
        c = self.c
        # beta_i: per-player logistic slope on minutes continuously on floor, with the
        # E1-all logit of each shot as offset
        all_model = models.fit_shot_model(self.lg.shots, include_shot_type=True, name="E1-all")
        c.audit.models.append(("E1-all", "lambda", all_model.lam))
        p = np.clip(all_model.predict(self.lg.shots), 1e-12, 1 - 1e-12)
        sh = self.lg.shots.assign(offset=np.log(p / (1 - p)))
        ps = self.lg.pbp_shots[np.isfinite(self.lg.pbp_shots["minutes_on"])]
        j = ps.merge(sh[["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "SHOT_MADE_FLAG", "offset"]],
                     left_on=["game_id", "event_id"], right_on=["GAME_ID", "GAME_EVENT_ID"], how="inner")
        j = j[j["PLAYER_ID"].isin(c.ids)]
        beta, se = {}, {}
        for pid, g in j.groupby("PLAYER_ID"):
            beta[pid], se[pid] = models.logistic_slope(g["SHOT_MADE_FLAG"], g["minutes_on"], g["offset"])
        b = c.series(pd.Series(beta, dtype=float), fill=np.nan)
        s2_ = c.series(pd.Series(se, dtype=float) ** 2, fill=np.nan)
        b_star, bp = c.s3("attribute", "Stamina beta", b, s2_, prior_mean=None)

        st = self.lg.player_stints
        g = st.groupby("player_id")["minutes"].agg(["mean", "var", "size"])
        g["var"] = g["var"].fillna(0.0)
        pooled = ((g["size"] - 1) * g["var"]).sum() / (g["size"] - 1).clip(lower=0).sum()
        n = c.series(g["size"])
        mean_len = c.series(g["mean"], fill=np.nan)
        len_star, lp = c.s3("attribute", "stint length", mean_len, safe_div(np.full(len(n), pooled), n),
                            prior_mean=None)

        mins = c.col("SPEED_MIN")
        dist48 = 48.0 * safe_div(c.col("DIST_MILES_OFF") + c.col("DIST_MILES_DEF"), mins)
        z_dist = self.tracking_residual_z(dist48, "distance per 48 minutes")
        comps = {}
        for name, v, prior in (("Z(beta*)", b_star, bp), ("Z(stint length*)", len_star, lp)):
            if prior.tau2 == 0:
                c.audit.note("stamina", f"{name}: tau^2 = 0, component drops out (doc 02)")
            else:
                comps[name] = (v, Z(v))
        comps["z(distance per 48 residual)"] = (dist48, z_dist)
        return self._rule_b("stamina", comps)


def derive_attributes(ctx, lg, all_ids):
    """Returns (rows, failures, builder). rows: player_id, attribute, score, percentile,
    rating, placeholder. The builder is returned so traits reuse the same shrunk values."""
    builder = AttributeBuilder(ctx, lg)
    frames, failures = [], {}
    missing = pd.Index(all_ids).difference(ctx.ids)
    for key in ATTRIBUTES:
        try:
            score = np.asarray(getattr(builder, key)(), float)
            if np.any(~np.isfinite(score)):
                bad = list(ctx.ids[~np.isfinite(score)][:20])
                raise DerivationError(f"Score undefined for {int((~np.isfinite(score)).sum())} "
                                      f"player(s): {bad}")
            r = rating(score)
        except Exception as e:      # noqa: BLE001 - reported per field
            failures[key] = ("abort" if type(e).__name__ == "ProportionViolation" else "failed",
                             f"{type(e).__name__}: {e}")
            continue
        frames.append(pd.DataFrame({"player_id": ctx.ids, "attribute": key, "score": score,
                                    "percentile": pct(score), "rating": r, "placeholder": 0}))
        if len(missing):
            frames.append(pd.DataFrame({"player_id": missing, "attribute": key, "score": np.nan,
                                        "percentile": np.nan, "rating": PLACEHOLDER_RATING,
                                        "placeholder": 1}))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["player_id", "attribute", "score", "percentile", "rating", "placeholder"])
    return out, failures, builder
