"""Empirical-Bayes shrinkage, exactly as specified in doc 02 "Volume adjustment".

Every prior is fit by method of moments on the real league-wide distribution of
per-player rates, with the observed variance corrected for sampling noise. No
cutoffs, no hand-picked prior strengths.

Players with zero opportunities carry no information about the prior, so they
are left out of the fit; they still receive a shrunk value (the prior mean).
"""

from dataclasses import dataclass

import numpy as np


class ShrinkageError(ValueError):
    pass


@dataclass(frozen=True)
class BetaPrior:
    """alpha = beta = inf means the method of moments found no between-player
    variance beyond sampling noise: the prior is a point mass at `mean`."""
    alpha: float
    beta: float
    mean: float
    n_players: int

    def posterior_mean(self, successes, opportunities):
        s = np.asarray(successes, dtype=float)
        n = np.asarray(opportunities, dtype=float)
        if np.isinf(self.alpha):
            return np.full(np.broadcast(s, n).shape, self.mean)
        return (s + self.alpha) / (n + self.alpha + self.beta)


@dataclass(frozen=True)
class GammaPrior:
    """Gamma prior in (shape k, mean theta) form, matching doc 02's formula
    shrunk = (points + k) / (possessions + k/theta): the posterior mean of a
    Poisson rate under a Gamma prior with shape k and rate k/theta."""
    k: float
    theta: float
    n_players: int

    @property
    def mean(self):
        return self.theta

    def posterior_mean(self, counts, exposure):
        x = np.asarray(counts, dtype=float)
        e = np.asarray(exposure, dtype=float)
        if np.isinf(self.k):
            return np.full(np.broadcast(x, e).shape, self.theta)
        return (x + self.k) / (e + self.k / self.theta)


def _validate(successes, opportunities, bounded):
    s = np.asarray(successes, dtype=float)
    n = np.asarray(opportunities, dtype=float)
    if s.shape != n.shape:
        raise ShrinkageError("successes and opportunities differ in shape")
    if np.any(~np.isfinite(s)) or np.any(~np.isfinite(n)):
        raise ShrinkageError("non-finite input")
    if np.any(s < 0) or np.any(n < 0):
        raise ShrinkageError("negative count")
    if bounded and np.any(s > n + 1e-9):
        bad = int(np.sum(s > n + 1e-9))
        raise ShrinkageError(f"{bad} player(s) have successes > opportunities; "
                             "not a proportion, Beta-Binomial does not apply")
    return s, n


def fit_beta_binomial(successes, opportunities):
    """Doc 02: mean and variance of per-player rates, variance corrected by
    subtracting mean(p(1-p)/n), then solved for alpha and beta."""
    s, n = _validate(successes, opportunities, bounded=True)
    mask = n > 0
    if mask.sum() < 2:
        raise ShrinkageError("need at least two players with opportunities to fit a prior")
    p = s[mask] / n[mask]
    m = p.mean()
    var_obs = p.var()
    noise = np.mean(p * (1 - p) / n[mask])
    var_true = var_obs - noise
    if m <= 0 or m >= 1:
        raise ShrinkageError(f"league mean rate {m} is degenerate")
    if var_true <= 0:
        return BetaPrior(np.inf, np.inf, m, int(mask.sum()))
    total = m * (1 - m) / var_true - 1
    if total <= 0:
        raise ShrinkageError("between-player variance exceeds the Bernoulli maximum")
    return BetaPrior(m * total, (1 - m) * total, m, int(mask.sum()))


def fit_gamma_poisson(counts, exposure):
    """Doc 02: same method of moments on per-player rates, observed variance
    corrected for Poisson noise (mean of rate/exposure)."""
    x, e = _validate(counts, exposure, bounded=False)
    mask = e > 0
    if mask.sum() < 2:
        raise ShrinkageError("need at least two players with exposure to fit a prior")
    r = x[mask] / e[mask]
    m = r.mean()
    if m <= 0:
        raise ShrinkageError("league mean rate is zero")
    var_true = r.var() - np.mean(r / e[mask])
    if var_true <= 0:
        return GammaPrior(np.inf, m, int(mask.sum()))
    return GammaPrior(m * m / var_true, m, int(mask.sum()))


@dataclass(frozen=True)
class ScaledInvChi2Prior:
    nu0: float
    tau0_sq: float
    n_players: int

    @property
    def mean(self):
        if np.isinf(self.nu0):
            return self.tau0_sq
        return self.nu0 * self.tau0_sq / (self.nu0 - 2)

    def posterior_mean(self, sample_var, dof):
        s2 = np.asarray(sample_var, dtype=float)
        nu = np.asarray(dof, dtype=float)
        if np.isinf(self.nu0):
            return np.full(np.broadcast(s2, nu).shape, self.tau0_sq)
        return (self.nu0 * self.tau0_sq + nu * s2) / (self.nu0 + nu - 2)


def fit_scaled_inv_chi2(sample_var, dof):
    """Doc 02/04 prior on variance, by method of moments on per-player sample
    variances with the chi-square sampling noise removed.

    For s^2 with nu degrees of freedom, E[s^2 | sigma^2] = sigma^2 and
    Var(s^2 | sigma^2) = 2 sigma^4 / nu; sigma^4 is estimated unbiasedly as
    s^4 nu/(nu+2). Matching mean M and corrected variance V to the
    Scaled-Inv-Chi2(nu0, tau0^2) moments gives nu0 = 4 + 2 M^2/V and
    tau0^2 = M (nu0 - 2)/nu0.
    """
    s2 = np.asarray(sample_var, dtype=float)
    nu = np.asarray(dof, dtype=float)
    mask = nu > 0
    if mask.sum() < 2:
        raise ShrinkageError("need at least two players with variance estimates")
    s2m, num = s2[mask], nu[mask]
    big_m = s2m.mean()
    v = s2m.var() - np.mean(2 * s2m ** 2 / (num + 2))
    if v <= 0:
        return ScaledInvChi2Prior(np.inf, big_m, int(mask.sum()))
    nu0 = 4 + 2 * big_m ** 2 / v
    return ScaledInvChi2Prior(nu0, big_m * (nu0 - 2) / nu0, int(mask.sum()))
