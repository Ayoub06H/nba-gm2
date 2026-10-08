import numpy as np
import pytest

from nbagm.shrinkage import (ProportionViolation, fit_s1, fit_s2, fit_scaled_inv_chi2, s1, s2,
                             s3, s4)


def test_s1_recovers_known_prior():
    rng = np.random.default_rng(0)
    true = rng.beta(30, 70, size=4000)
    n = rng.integers(50, 600, size=4000)
    s = rng.binomial(n, true)
    prior = fit_s1(s, n)
    assert prior.mean == pytest.approx(0.3, abs=0.005)
    assert prior.alpha + prior.beta == pytest.approx(100, rel=0.15)


def test_s1_guard_names_the_offenders():
    with pytest.raises(ProportionViolation) as e:
        s1([12, 3, 5], [10, 10, 10], name="FTA/FGA", ids=[101, 102, 103])
    assert "FTA/FGA" in str(e.value) and "101" in str(e.value)
    assert e.value.offenders[0][0] == 101


def test_s1_zero_opportunity_gets_prior_mean():
    shrunk, prior = s1([10, 20, 30, 0], [100, 100, 100, 0])
    assert prior.n_players == 3 and shrunk[3] == pytest.approx(prior.mean)


def test_s2_formula_matches_doc():
    rng = np.random.default_rng(2)
    rates = rng.gamma(25, 1 / 25, size=3000)
    e = rng.integers(20, 300, size=3000).astype(float)
    c = rng.poisson(rates * e)
    prior = fit_s2(c, e)
    assert prior.m == pytest.approx(1.0, abs=0.02)
    assert prior.k == pytest.approx(25, rel=0.25)
    shrunk, _ = s2(c, e)
    assert shrunk[0] == pytest.approx((c[0] + prior.k) / (e[0] + prior.k / prior.m))


def test_s3_shrinks_noisy_differences_toward_zero():
    rng = np.random.default_rng(3)
    true = rng.normal(0, 0.05, size=2000)
    s2_ = rng.uniform(0.001, 0.01, size=2000)
    d = true + rng.normal(0, np.sqrt(s2_))
    shrunk, prior = s3(d, s2_)
    assert prior.tau2 == pytest.approx(0.0025, rel=0.15)
    assert np.all(np.abs(shrunk) <= np.abs(d) + 1e-12)
    out, _ = s3(np.array([0.1, -0.1, np.nan]), np.array([1e-9, 1e-9, np.nan]))
    assert out[2] == 0.0                       # no attempts -> prior mean


def test_s3_no_true_spread_sets_everyone_to_the_prior():
    out, prior = s3(np.array([0.1, -0.1, 0.05, -0.05]), np.array([1.0, 1.0, 1.0, 1.0]))
    assert prior.tau2 == 0 and np.all(out == 0)


def test_s4_relative_risk():
    rng = np.random.default_rng(4)
    true = rng.gamma(10, 1 / 10, size=3000)
    e = rng.uniform(20, 200, size=3000)
    o = rng.poisson(true * e)
    rr, prior = s4(o, e)
    assert 1 / prior.k == pytest.approx(0.1, rel=0.3)
    assert rr[0] == pytest.approx((o[0] + prior.k) / (e[0] + prior.k))
    rr0, _ = s4(np.array([0.0, 3, 5]), np.array([0.0, 2, 6]))
    assert rr0[0] == 1.0


def test_scaled_inv_chi2_uses_doc_formula():
    rng = np.random.default_rng(5)
    nu0, s0 = 20.0, 4.0
    sigma2 = nu0 * s0 / rng.chisquare(nu0, size=5000)
    n = rng.integers(11, 81, size=5000)
    s2_ = sigma2 * rng.chisquare(n - 1) / (n - 1)
    prior = fit_scaled_inv_chi2(s2_, n)
    assert prior.nu0 == pytest.approx(nu0, rel=0.3)
    got = prior.shrink([9.0, 9.0], [1, 31])
    assert got[0] == pytest.approx(prior.s0_sq)
    assert got[1] == pytest.approx((prior.nu0 * prior.s0_sq + 30 * 9.0) / (prior.nu0 + 30))
