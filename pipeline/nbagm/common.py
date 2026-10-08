"""Shared pieces of the derivations: the population, doc 02's percentile / Z / rating
definitions, a shrinkage context that records every fitted prior, and the audit
trail written to the league file.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import shrinkage as sh


class DerivationError(ValueError):
    """A field could not be derived from the real data as the docs define it."""


def pct(x):
    """Doc 02 mid-rank percentile: (#lower + 0.5 * #tied) / N, ties including himself."""
    x = np.asarray(x, dtype=float)
    if np.any(~np.isfinite(x)):
        raise DerivationError("percentile of a component with undefined values")
    order = np.sort(x)
    lower = np.searchsorted(order, x, side="left")
    tied = np.searchsorted(order, x, side="right") - lower
    return (lower + 0.5 * tied) / len(x)


def Z(x):
    """Doc 02: Z(x) = inverse normal CDF of the mid-rank percentile."""
    return norm.ppf(pct(x))


def zstd(x):
    """Standard score (x - mean) / SD across the population (doc 02 lower-case z, doc 04).
    A component with no spread at all is 0 for everyone, not 0/0."""
    x = np.asarray(x, dtype=float)
    if np.any(~np.isfinite(x)):
        raise DerivationError("z-score of a component with undefined values")
    sd = x.std()
    if sd <= 1e-12 * max(1.0, abs(x.mean())):
        return np.zeros_like(x)
    return (x - x.mean()) / sd


def rating(score):
    """Doc 02: Rating = 99 x pct(Score), unrounded."""
    return 99.0 * pct(score)


def safe_div(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b != 0, a / b, np.nan)


@dataclass
class Audit:
    priors: list = field(default_factory=list)       # dicts
    components: list = field(default_factory=list)   # DataFrames: player_id, field, component, value, z
    weights: list = field(default_factory=list)      # (field, component, weight)
    notes: list = field(default_factory=list)        # (field, text)
    models: list = field(default_factory=list)       # (name, key, value)

    def note(self, fld, text):
        self.notes.append((fld, text))


class Ctx:
    """Population-aligned access to inputs plus shrinkage that records its priors.
    `ids` is the population (rostered players with exposure); every array returned
    is aligned with it."""

    def __init__(self, inputs, ids, audit):
        self.ids = pd.Index(ids, name="player_id")
        self.inputs = inputs.reindex(self.ids, fill_value=0.0)
        self.audit = audit
        self._memo = {}

    def _cached(self, key, fn):
        """A statistic used by several fields is shrunk once, under one name."""
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    def col(self, name):
        return self.inputs[name].to_numpy(dtype=float)

    def series(self, values, fill=0.0):
        """Align a player_id-indexed Series with the population."""
        return values.reindex(self.ids).fillna(fill).to_numpy(dtype=float)

    def _prior(self, kind, name, family, p1, p2, mean, n):
        self.audit.priors.append(dict(kind=kind, name=name, family=family,
                                      param1=_finite(p1), param2=_finite(p2),
                                      mean=_finite(mean), n_players=int(n)))

    def s1(self, kind, name, successes, opportunities):
        return self._cached(("s1", name), lambda: self._s1(kind, name, successes, opportunities))

    def _s1(self, kind, name, successes, opportunities):
        out, p = sh.s1(successes, opportunities, name=name, ids=self.ids.to_numpy())
        self._prior(kind, name, "beta", p.alpha, p.beta, p.mean, p.n_players)
        return out

    def s2(self, kind, name, counts, exposure):
        return self._cached(("s2", name), lambda: self._s2(kind, name, counts, exposure))

    def _s2(self, kind, name, counts, exposure):
        counts = np.asarray(counts, float)
        if np.any(counts < 0):
            bad = [(int(i), float(c)) for i, c in zip(self.ids, counts) if c < 0][:15]
            raise DerivationError(f"{name}: Gamma-Poisson (S2) needs non-negative counts; negative "
                                  f"for {int((counts < 0).sum())} player(s): {bad}")
        out, p = sh.s2(counts, exposure, name=name)
        self._prior(kind, name, "gamma", p.k, p.m, p.m, p.n_players)
        return out

    def s3(self, kind, name, d, s2_, prior_mean=0.0):
        out, p = sh.s3(d, s2_, prior_mean=prior_mean, name=name)
        self._prior(kind, name, "normal", p.tau2, None, p.mean, p.n_players)
        if p.tau2 == 0:
            self.audit.note(name, "S3: tau^2 = 0, no detectable true spread; set to the prior "
                                  "mean for everyone")
        return out, p

    def s4(self, kind, name, observed, expected):
        out, p = sh.s4(observed, expected, name=name)
        self._prior(kind, name, "gamma_rr", p.k, None, 1.0, p.n_players)
        return out

    def log(self, fld, component, value, z=None):
        self.audit.components.append(pd.DataFrame({
            "player_id": self.ids, "field": fld, "component": component,
            "value": np.asarray(value, float),
            "z": np.full(len(self.ids), np.nan) if z is None else np.asarray(z, float)}))


def _finite(v):
    if v is None:
        return None
    v = float(v)
    return v if np.isfinite(v) else None
