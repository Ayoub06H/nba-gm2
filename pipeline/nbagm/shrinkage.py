"""The four shrinkage families of doc 02 ("Shrinkage: four families"), plus the
Scaled-Inverse-Chi-Squared prior doc 04 uses for Consistency.

Every prior is fit by method of moments on the real distribution of that exact
statistic across the population; nothing is hand-picked. Players with no
opportunities/exposure carry no information about the prior, so they are left
out of the fit and receive the prior value.
"""

from dataclasses import dataclass

import numpy as np


class ShrinkageError(ValueError):
    pass


class ProportionViolation(ShrinkageError):
    """S1 build guard (doc 02, doc 03): successes > opportunities for some player."""

    def __init__(self, name, offenders):
        self.name, self.offenders = name, offenders
        shown = ", ".join(f"{pid} ({s:g} > {n:g})" for pid, s, n in offenders[:15])
        super().__init__(f"{name}: numerator exceeds denominator for {len(offenders)} "
                         f"player(s): {shown}. The definition must be fixed in the doc; "
                         "nothing is clipped.")


def _arr(x):
    return np.asarray(x, dtype=float)


# --------------------------------------------------------------------------- #
# S1 - Beta-Binomial, for true proportions
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class BetaPrior:
    """alpha = beta = inf: no between-player variance beyond sampling noise, so the
    prior is a point mass at `mean`."""
    alpha: float
    beta: float
    mean: float
    n_players: int

    def shrink(self, successes, opportunities):
        s, n = _arr(successes), _arr(opportunities)
        if np.isinf(self.alpha):
            return np.full(np.broadcast(s, n).shape, self.mean)
        return (s + self.alpha) / (n + self.alpha + self.beta)

    posterior_mean = shrink


def guard_proportion(name, successes, opportunities, ids=None):
    s, n = _arr(successes), _arr(opportunities)
    if np.any(~np.isfinite(s)) or np.any(~np.isfinite(n)) or np.any(s < 0) or np.any(n < 0):
        raise ShrinkageError(f"{name}: negative or non-finite count")
    bad = np.flatnonzero(s > n + 1e-9)
    if len(bad):
        ids = np.arange(len(s)) if ids is None else np.asarray(ids)
        raise ProportionViolation(name, [(ids[i], s[i], n[i]) for i in bad])


def fit_s1(successes, opportunities, name="proportion", ids=None):
    """m = mean of observed rates; v = their variance minus mean(p(1-p)/n);
    alpha+beta = m(1-m)/v - 1; alpha = m(alpha+beta)."""
    guard_proportion(name, successes, opportunities, ids)
    s, n = _arr(successes), _arr(opportunities)
    mask = n > 0
    if mask.sum() < 2:
        raise ShrinkageError(f"{name}: fewer than two players with opportunities")
    p = s[mask] / n[mask]
    m = p.mean()
    if m <= 0 or m >= 1:
        raise ShrinkageError(f"{name}: league mean rate {m} is degenerate")
    v = p.var() - np.mean(p * (1 - p) / n[mask])
    if v <= 0:
        return BetaPrior(np.inf, np.inf, m, int(mask.sum()))
    total = m * (1 - m) / v - 1
    if total <= 0:
        raise ShrinkageError(f"{name}: between-player variance exceeds the Bernoulli maximum")
    return BetaPrior(m * total, (1 - m) * total, m, int(mask.sum()))


def s1(successes, opportunities, name="proportion", ids=None):
    prior = fit_s1(successes, opportunities, name, ids)
    return prior.shrink(successes, opportunities), prior


# --------------------------------------------------------------------------- #
# S2 - Gamma-Poisson, for counts per unit of exposure
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GammaPrior:
    """Shape k and prior mean m: shrunk = (c + k) / (E + k/m) (doc 02 S2)."""
    k: float
    m: float
    n_players: int

    @property
    def mean(self):
        return self.m

    theta = mean

    def shrink(self, counts, exposure):
        c, e = _arr(counts), _arr(exposure)
        if np.isinf(self.k):
            return np.full(np.broadcast(c, e).shape, self.m)
        return (c + self.k) / (e + self.k / self.m)

    posterior_mean = shrink


def fit_s2(counts, exposure, name="rate"):
    """r_i = c_i/E_i; m = mean(r); v = var(r) - mean(m/E_i); k = m^2/v."""
    c, e = _arr(counts), _arr(exposure)
    if np.any(c < 0) or np.any(e < 0) or np.any(~np.isfinite(c)) or np.any(~np.isfinite(e)):
        raise ShrinkageError(f"{name}: negative or non-finite count/exposure")
    mask = e > 0
    if mask.sum() < 2:
        raise ShrinkageError(f"{name}: fewer than two players with exposure")
    r = c[mask] / e[mask]
    m = r.mean()
    if m <= 0:
        raise ShrinkageError(f"{name}: league mean rate is zero")
    v = r.var() - np.mean(m / e[mask])
    if v <= 0:
        return GammaPrior(np.inf, m, int(mask.sum()))
    return GammaPrior(m * m / v, m, int(mask.sum()))


def s2(counts, exposure, name="rate"):
    prior = fit_s2(counts, exposure, name)
    return prior.shrink(counts, exposure), prior


# --------------------------------------------------------------------------- #
# S3 - Normal-Normal, for differences from an expected value
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class NormalPrior:
    mean: float
    tau2: float
    n_players: int


def s3(d, s2_, prior_mean=0.0, name="delta"):
    """tau^2 = max(0, Var(d) - mean(s^2)); d* = mean + (d - mean) tau^2/(tau^2 + s^2).
    Players without a defined d (no attempts) get the prior mean. With tau^2 = 0 the
    statistic has no detectable true spread and everyone gets the prior mean."""
    d, s2_ = _arr(d), _arr(s2_)
    ok = np.isfinite(d) & np.isfinite(s2_) & (s2_ > 0)
    if ok.sum() < 2:
        raise ShrinkageError(f"{name}: fewer than two players with a defined difference")
    mean = d[ok].mean() if prior_mean is None else prior_mean
    tau2 = max(0.0, float(np.var(d[ok]) - np.mean(s2_[ok])))
    out = np.full(d.shape, mean, dtype=float)
    if tau2 > 0:
        out[ok] = mean + (d[ok] - mean) * tau2 / (tau2 + s2_[ok])
    return out, NormalPrior(mean, tau2, int(ok.sum()))


# --------------------------------------------------------------------------- #
# S4 - Poisson-Gamma relative risk, for observed / expected event counts
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RelativeRiskPrior:
    k: float
    n_players: int


def s4(observed, expected, name="relative risk"):
    """RR = O/E; prior Gamma(k, k) with 1/k = max(0, Var(RR) - mean(1/E));
    RR* = (O + k)/(E + k). No exposure -> RR* = 1 (the prior mean)."""
    o, e = _arr(observed), _arr(expected)
    mask = e > 0
    if mask.sum() < 2:
        raise ShrinkageError(f"{name}: fewer than two players with expected events")
    rr = o[mask] / e[mask]
    inv_k = max(0.0, float(rr.var() - np.mean(1 / e[mask])))
    out = np.ones(o.shape)
    if inv_k == 0:
        return out, RelativeRiskPrior(np.inf, int(mask.sum()))
    k = 1 / inv_k
    out[mask] = (o[mask] + k) / (e[mask] + k)
    return out, RelativeRiskPrior(k, int(mask.sum()))


# --------------------------------------------------------------------------- #
# Scaled-Inverse-Chi-Squared, for Consistency's variances (doc 04)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ScaledInvChi2Prior:
    nu0: float
    s0_sq: float
    n_players: int

    def shrink(self, sample_var, n_games):
        """Doc 04: s*^2 = (nu0 s0^2 + (n-1) s^2) / (nu0 + n - 1); fewer than two games
        carry no variance information, so they get s0^2."""
        s2_, n = _arr(sample_var), _arr(n_games)
        dof = np.where(n >= 2, n - 1, 0.0)
        s2_ = np.where(dof > 0, s2_, 0.0)
        if np.isinf(self.nu0):
            return np.full(s2_.shape, self.s0_sq)
        return (self.nu0 * self.s0_sq + dof * s2_) / (self.nu0 + dof)


def fit_scaled_inv_chi2(sample_var, n_games):
    """Method of moments on per-player sample variances (dof = n - 1), with the
    chi-square sampling noise removed: E[s^2] = sigma^2, Var(s^2|sigma^2) = 2 sigma^4/nu,
    sigma^4 estimated as s^4 nu/(nu+2). Matching the Scaled-Inv-Chi2(nu0, s0^2) moments
    gives nu0 = 4 + 2 M^2/V and s0^2 = M (nu0 - 2)/nu0."""
    s2_, n = _arr(sample_var), _arr(n_games)
    mask = n >= 2
    if mask.sum() < 2:
        raise ShrinkageError("fewer than two players with at least two games")
    s2m, nu = s2_[mask], n[mask] - 1
    big_m = s2m.mean()
    v = s2m.var() - np.mean(2 * s2m ** 2 / (nu + 2))
    if v <= 0:
        return ScaledInvChi2Prior(np.inf, big_m, int(mask.sum()))
    nu0 = 4 + 2 * big_m ** 2 / v
    return ScaledInvChi2Prior(nu0, big_m * (nu0 - 2) / nu0, int(mask.sum()))
